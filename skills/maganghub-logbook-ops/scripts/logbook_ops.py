#!/usr/bin/env python3
"""Generic zero-dependency CLI for MagangHub Monev daily logbook ops.

Pure Python 3.9+ standard library only. Supports gate-verified auto-submit
by default with ``--draft-only`` manual-review opt-out, while strictly
enforcing no auth/CAPTCHA/geofence bypasses and no overwriting already-submitted dates.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import check_report as gate
import collect_today as collector

BASELINE_MINUTES_DEFAULT = 18.0
MIN_FIELD_CHARS = gate.MIN_CHARS
WARN_MIN_FIELD_CHARS = 140
MAX_FIELD_CHARS = gate.MAX_CHARS
WARN_MAX_FIELD_CHARS = 1200
DUPLICATE_JACCARD_THRESHOLD = 0.65

MONEV_BASE_URL = "https://monev.maganghub.kemnaker.go.id"
MONEV_PREFLIGHT_URL = f"{MONEV_BASE_URL}/dashboard/evaluasi"
MONEV_FORM_FIELDS = [
    ("aktivitas", "uraian_aktivitas", "Uraian aktivitas", "Tulis uraian aktivitas minimal 100 karakter"),
    ("pelajaran", "pembelajaran", "Pembelajaran yang diperoleh", "Tulis ilmu/pembelajaran yang diperoleh minimal 100 karakter"),
    ("kendala", "kendala", "Kendala yang dialami", "Tulis kendala/hambatan yang dialami minimal 100 karakter"),
]
MONEV_CONFIRM_CHECKBOX_LABEL = "Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar"
MONEV_SUBMIT_BUTTON_LABEL = "Simpan dan Kirim"
SUBMITTED_STATUSES = {"SUBMITTED_BY_HUMAN", "AUTO_SUBMITTED"}

LOGBOOK_FIELDS = [
    "date",
    "status",
    "uraian_aktivitas",
    "pembelajaran",
    "kendala",
    "char_counts",
    "warnings",
    "raw_notes_summary",
    "updated_at",
]

METRICS_FIELDS = [
    "date",
    "baseline_minutes",
    "actual_minutes",
    "saved_minutes",
    "status",
    "mentor_revisions",
    "notes",
]

NUMBER_TOKEN_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:v|kv|kva|kw|w|a|ma|ah|mm2|mm²|ohm|hz|%|ms|s|kb|mb|gb|inci|inch|inti|kutub|titik|unit|fasa|jam|m)\b",
    re.IGNORECASE,
)

WORD_RE = re.compile(r"[a-z0-9]{4,}", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(date_str: str) -> dt.date:
    if not ISO_DATE_RE.match(date_str):
        raise ValueError(f"Invalid ISO date (expected YYYY-MM-DD): {date_str}")
    return dt.date.fromisoformat(date_str)


def _normalize_num_token(tok: str) -> str:
    clean = tok.lower().replace("mm²", "mm2").replace(",", ".")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _extract_numeric_tokens(text: str) -> set[str]:
    return {_normalize_num_token(m.group(0)) for m in NUMBER_TOKEN_RE.finditer(text)}


def _extract_raw_numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", ".").lower() for m in re.finditer(r"\b\d+(?:[.,]\d+)?\b", text)}


def _find_unverified_numbers(combined: str, raw_notes: str) -> list[str]:
    if not raw_notes.strip():
        return []
    raw_nums = _extract_raw_numbers(raw_notes)
    draft_tokens = _extract_numeric_tokens(combined)
    warnings: list[str] = []
    for tok in sorted(draft_tokens):
        m = re.match(r"^(\d+(?:\.\d+)?)", tok)
        core = m.group(1) if m else tok
        matched = core in raw_nums
        if not matched:
            try:
                val = float(core)
                for rn in raw_nums:
                    try:
                        if abs(float(rn) - val) < 1e-9:
                            matched = True
                            break
                    except ValueError:
                        pass
            except ValueError:
                pass
        if not matched:
            warnings.append(f"UNVERIFIED_NUMBER:{tok}")
    return warnings


def _content_words(text: str) -> set[str]:
    stopwords = {
        "yang", "untuk", "dengan", "pada", "dari", "agar", "juga",
        "dalam", "serta", "masih", "perlu", "saat", "oleh", "atau", "akan",
        "telah", "harus", "tidak", "bisa", "dapat", "tiap", "setiap",
    }
    return {w.lower() for w in WORD_RE.findall(text) if w.lower() not in stopwords}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def validate_entry(
    *,
    entry_date: str,
    uraian: str,
    pembelajaran: str,
    kendala: str,
    raw_notes: str = "",
    sensitive_terms: list[str] | None = None,
    existing_rows: list[dict[str, str]] | None = None,
    enforce_delivery_gate: bool = True,
) -> dict[str, Any]:
    _parse_date(entry_date)
    errors: list[str] = []
    warnings: list[str] = []

    fields = {
        "uraian_aktivitas": uraian.replace("\r\n", "\n").strip(),
        "pembelajaran": pembelajaran.replace("\r\n", "\n").strip(),
        "kendala": kendala.replace("\r\n", "\n").strip(),
    }
    char_counts = {k: len(v) for k, v in fields.items()}
    combined = "\n".join(fields.values())

    for name, val in fields.items():
        n = len(val)
        if n < MIN_FIELD_CHARS:
            errors.append(f"TOO_SHORT:{name}={n} (<{MIN_FIELD_CHARS})")
        elif n < WARN_MIN_FIELD_CHARS:
            warnings.append(f"SHORT_FIELD:{name}={n} (<{WARN_MIN_FIELD_CHARS})")
        if n > MAX_FIELD_CHARS:
            errors.append(f"TOO_LONG:{name}={n} (>{MAX_FIELD_CHARS})")
        elif n > WARN_MAX_FIELD_CHARS:
            warnings.append(f"LONG_FIELD:{name}={n} (>{WARN_MAX_FIELD_CHARS})")

    for code, pat in gate.SECRET_PATTERNS:
        if pat.search(combined):
            errors.append(f"CREDENTIAL_LEAK_BLOCKED:{code}")

    for code, pat in gate.SAFETY_BOUNDARY_RULES:
        if pat.search(combined):
            errors.append(f"CLAIM_BOUNDARY_VIOLATION:{code}")

    for term in sensitive_terms or []:
        t = term.strip()
        if t and gate.compile_term_pattern(t).search(combined):
            errors.append(f"SENSITIVE_TERM_LEAK:{t}")

    warnings.extend(_find_unverified_numbers(combined, raw_notes))

    prior = [r for r in (existing_rows or []) if r.get("date") != entry_date][-3:]
    cur_words = _content_words(combined)
    for row in prior:
        prev_text = " ".join(
            [row.get("uraian_aktivitas", ""), row.get("pembelajaran", ""), row.get("kendala", "")]
        )
        sim = _jaccard(cur_words, _content_words(prev_text))
        if sim >= DUPLICATE_JACCARD_THRESHOLD:
            warnings.append(f"DUPLICATE_DRIFT_ALERT:date={row.get('date')},jaccard={sim:.2f}")

    result: dict[str, Any] = {
        "ok": len(errors) == 0,
        "date": entry_date,
        "char_counts": char_counts,
        "errors": errors,
        "warnings": warnings,
    }

    if enforce_delivery_gate:
        dg = gate.evaluate_report(
            {
                "aktivitas": fields["uraian_aktivitas"],
                "pelajaran": fields["pembelajaran"],
                "kendala": fields["kendala"],
            },
            safety_checks=False,
        )
        for chk in dg["failed_checks"]:
            errors.append(f"DELIVERY_GATE_FAIL:{chk['id']}:{chk['message']}")
        result["ok"] = len(errors) == 0
        result["delivery_gate"] = {
            "ok": dg["ok"],
            "passed": dg["passed"],
            "total": dg["total"],
            "failed_checks": dg["failed_checks"],
        }

    return result


def _write_paste_file(draft_dir: Path, entry_date: str, uraian: str, pembelajaran: str, kendala: str, result: dict[str, Any]) -> Path:
    draft_dir.mkdir(parents=True, exist_ok=True)
    out_path = draft_dir / f"{entry_date}_report.txt"
    warn_text = ", ".join(result["warnings"]) if result["warnings"] else "NONE"
    edit_url = f"{MONEV_BASE_URL}/dashboard/riwayat?date={entry_date}&view=edit"
    content = (
        f"MAGANGHUB MONEV LOGBOOK DRAFT — {entry_date}\n"
        f"STATUS: DRAFT_PENDING_SUBMIT (COPY-PASTE FALLBACK IF BROWSER/LOGIN/GEOFENCE UNAVAILABLE)\n"
        f"PORTAL EDIT URL: {edit_url}\n"
        f"CHAR COUNTS: {json.dumps(result['char_counts'])}\n"
        f"WARNINGS: {warn_text}\n"
        f"{'=' * 72}\n\n"
        f"[1. Uraian aktivitas]\n{uraian.strip()}\n\n"
        f"[2. Pembelajaran yang diperoleh]\n{pembelajaran.strip()}\n\n"
        f"[3. Kendala yang dialami]\n{kendala.strip()}\n\n"
        f"{'=' * 72}\n"
        f"AFTER SUBMITTING, RECORD YOUR ACTUAL TIME:\n"
        f"python scripts/logbook_ops.py confirm --date {entry_date} --actual-minutes <MINUTES> --revisions 0 --mode auto|human\n"
    )
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _resolve_three_fields(
    *,
    json_input: str = "",
    uraian: str = "",
    pembelajaran: str = "",
    kendala: str = "",
) -> tuple[str, str, str]:
    if json_input:
        with Path(json_input).open("r", encoding="utf-8") as f:
            payload = json.load(f)
        norm = gate.normalize_report_fields(payload)
        return norm["aktivitas"], norm["pelajaran"], norm["kendala"]
    return uraian, pembelajaran, kendala


def cmd_collect(args: argparse.Namespace) -> int:
    notes_parts = [args.notes] if args.notes else []
    if args.notes_file:
        notes_parts.append(Path(args.notes_file).read_text(encoding="utf-8"))
    manual_notes = "\n".join(p for p in notes_parts if p.strip())

    chat_dirs = [Path(p) for p in args.chat_dir] if args.chat_dir else None
    extra_repos = [Path(p) for p in args.repo]
    extra_terms = [t.strip() for t in (args.sensitive_terms or "").split(",") if t.strip()]

    evidence = collector.collect_evidence(
        args.date or None,
        chat_dirs=chat_dirs,
        extra_repos=extra_repos,
        manual_notes=manual_notes,
        include_chats=not args.no_chats,
        include_git=not args.no_git,
        author_override=args.author,
        sensitive_terms=extra_terms,
        redact_confidential=args.redact_confidential,
    )
    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    else:
        print(collector.format_evidence_markdown(evidence))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    if args.json_file:
        with Path(args.json_file).open("r", encoding="utf-8") as f:
            data = json.load(f)
    elif args.uraian or args.pembelajaran or args.kendala:
        data = {
            "aktivitas": args.uraian,
            "pelajaran": args.pembelajaran,
            "kendala": args.kendala,
        }
    else:
        print(json.dumps({"ok": False, "error": "Provide --json-file or --uraian/--pembelajaran/--kendala"}), file=sys.stderr)
        return 2

    extra_terms = [t.strip() for t in (args.sensitive_terms or "").split(",") if t.strip()]
    res = gate.evaluate_report(
        data,
        safety_checks=not args.no_safety_checks,
        sensitive_terms=extra_terms,
    )
    raw_notes = args.raw_notes or ""
    if args.raw_notes_file:
        raw_notes = Path(args.raw_notes_file).read_text(encoding="utf-8")
    norm = gate.normalize_report_fields(data)
    res["numeric_warnings"] = _find_unverified_numbers("\n".join(norm.values()), raw_notes)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for c in res["checks"]:
            print(("PASS " if c["ok"] else "FAIL ") + c["message"])
        for w in res["numeric_warnings"]:
            print(f"WARN {w}")
        status = "PASS" if res["ok"] else "FAIL"
        print(f"\n{status}: {res['passed']}/{res['total']} checks passed")

    return 0 if res["ok"] else 1


def cmd_record(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    log_csv = data_dir / "logbook.csv"
    met_csv = data_dir / "ops_metrics.csv"

    uraian, pembelajaran, kendala = _resolve_three_fields(
        json_input=args.json_input,
        uraian=args.uraian,
        pembelajaran=args.pembelajaran,
        kendala=args.kendala,
    )
    if not (uraian.strip() and pembelajaran.strip() and kendala.strip()):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "MISSING_FIELDS: Provide --json-input or all of --uraian, --pembelajaran, and --kendala.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    raw_notes = args.raw_notes or ""
    if args.raw_notes_file:
        raw_notes = Path(args.raw_notes_file).read_text(encoding="utf-8")

    existing = _read_csv_rows(log_csv)
    exists_same_date = any(r.get("date") == args.date for r in existing)
    if exists_same_date and not args.force_overwrite_confirmed:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"OVERWRITE_BLOCKED: Entry for {args.date} already exists. Pass --force-overwrite-confirmed after explicit YES.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    sensitive = [s.strip() for s in (args.sensitive_terms or "").split(",") if s.strip()]
    res = validate_entry(
        entry_date=args.date,
        uraian=uraian,
        pembelajaran=pembelajaran,
        kendala=kendala,
        raw_notes=raw_notes,
        sensitive_terms=sensitive,
        existing_rows=existing,
        enforce_delivery_gate=not args.skip_delivery_gate,
    )

    if not res["ok"] or (res["warnings"] and not args.allow_warnings):
        res["blocked_reason"] = "HARD_ERRORS" if not res["ok"] else "WARNINGS_REQUIRE_HUMAN_REVIEW"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    status = args.status
    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    new_row = {
        "date": args.date,
        "status": status,
        "uraian_aktivitas": uraian.strip(),
        "pembelajaran": pembelajaran.strip(),
        "kendala": kendala.strip(),
        "char_counts": json.dumps(res["char_counts"]),
        "warnings": "; ".join(res["warnings"]),
        "raw_notes_summary": raw_notes.strip().replace("\n", " ")[:240],
        "updated_at": now_iso,
    }
    updated_log = [r for r in existing if r.get("date") != args.date]
    updated_log.append(new_row)
    updated_log.sort(key=lambda r: r.get("date", ""))
    _write_csv_rows(log_csv, LOGBOOK_FIELDS, updated_log)

    draft_path = _write_paste_file(
        data_dir / "drafts", args.date, uraian, pembelajaran, kendala, res
    )

    metrics = _read_csv_rows(met_csv)
    actual_min = float(args.actual_minutes) if args.actual_minutes is not None else ""
    baseline_min = float(args.baseline_minutes)
    saved_min = round(baseline_min - actual_min, 2) if isinstance(actual_min, float) else ""
    new_met = {
        "date": args.date,
        "baseline_minutes": baseline_min,
        "actual_minutes": actual_min,
        "saved_minutes": saved_min,
        "status": status,
        "mentor_revisions": int(args.revisions),
        "notes": args.metric_note or "",
    }
    updated_met = [r for r in metrics if r.get("date") != args.date]
    updated_met.append(new_met)
    updated_met.sort(key=lambda r: r.get("date", ""))
    _write_csv_rows(met_csv, METRICS_FIELDS, updated_met)

    res["saved_logbook_csv"] = str(log_csv)
    res["saved_metrics_csv"] = str(met_csv)
    res["paste_ready_file"] = str(draft_path)
    res["status"] = status
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_prepare_fill(args: argparse.Namespace) -> int:
    _parse_date(args.date)
    data_dir = Path(args.data_dir)
    log_csv = data_dir / "logbook.csv"
    existing = _read_csv_rows(log_csv)
    row_by_date = {r.get("date"): r for r in existing if r.get("date")}

    existing_status = row_by_date[args.date].get("status", "") if args.date in row_by_date else ""
    if existing_status in SUBMITTED_STATUSES:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"ALREADY_SUBMITTED: {args.date} is already marked {existing_status}. Never overwrite a submitted report.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    if args.json_file:
        with Path(args.json_file).open("r", encoding="utf-8") as f:
            payload = json.load(f)
        norm = gate.normalize_report_fields(payload)
        uraian, pembelajaran, kendala = norm["aktivitas"], norm["pelajaran"], norm["kendala"]
    elif args.date in row_by_date:
        r = row_by_date[args.date]
        uraian = r.get("uraian_aktivitas", "")
        pembelajaran = r.get("pembelajaran", "")
        kendala = r.get("kendala", "")
    else:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"NOT_FOUND: No draft found for {args.date} in {log_csv} and no --json-file provided.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    sensitive = [s.strip() for s in (args.sensitive_terms or "").split(",") if s.strip()]
    res = validate_entry(
        entry_date=args.date,
        uraian=uraian,
        pembelajaran=pembelajaran,
        kendala=kendala,
        sensitive_terms=sensitive,
        existing_rows=existing,
        enforce_delivery_gate=True,
    )
    if not res["ok"]:
        res["blocked_reason"] = "SAFETY_OR_DELIVERY_GATE_FAILED"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    if getattr(args, "strict_warnings", False) and res["warnings"]:
        res["blocked_reason"] = "WARNINGS_BLOCKED_AUTO_SUBMIT"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    auto_submit = not getattr(args, "draft_only", False)
    submit_mode = "auto_submit" if auto_submit else "draft_only"
    confirm_mode = "auto" if auto_submit else "human"

    values = {
        "aktivitas": uraian.strip(),
        "pelajaran": pembelajaran.strip(),
        "kendala": kendala.strip(),
    }
    fields_payload = [
        {
            "key": json_key,
            "label": label,
            "placeholder": placeholder,
            "value": values[json_key],
            "char_count": len(values[json_key]),
        }
        for json_key, _csv_key, label, placeholder in MONEV_FORM_FIELDS
    ]

    paste_file = data_dir / "drafts" / f"{args.date}_report.txt"
    if not paste_file.exists():
        paste_file = _write_paste_file(data_dir / "drafts", args.date, uraian, pembelajaran, kendala, res)

    confirm_cmd = (
        f"python scripts/logbook_ops.py confirm --date {args.date} --actual-minutes <MINUTES> --revisions 0 --mode {confirm_mode}"
    )
    output = {
        "ok": True,
        "date": args.date,
        "submit_mode": submit_mode,
        "portal": {
            "preflight_url": MONEV_PREFLIGHT_URL,
            "edit_url": f"{MONEV_BASE_URL}/dashboard/riwayat?date={args.date}&view=edit",
            "logged_in_tabs": ["Beranda", "Riwayat", "Perkembangan", "Akun"],
            "confirmation_checkbox_label": MONEV_CONFIRM_CHECKBOX_LABEL,
            "submit_button_label": MONEV_SUBMIT_BUTTON_LABEL,
            "geofence_note": "MagangHub only accepts submissions for today's date at the placement location; stop and report server errors without marking submitted.",
            "reload_warning": "Open the tab once; never re-call browser.open on an already-open Monev edit tab.",
        },
        "submit_guards": {
            "tick_confirmation_checkbox": auto_submit,
            "click_simpan_dan_kirim": auto_submit,
            "verify_textarea_parity_before_submit": True,
            "verify_portal_success_before_confirm": True,
            "bypass_antibot_or_captcha": False,
            "bypass_geofence_or_sso": False,
        },
        "human_in_the_loop_guards": {
            "tick_confirmation_checkbox": auto_submit,
            "click_simpan_dan_kirim": auto_submit,
            "bypass_antibot_or_captcha": False,
        },
        "fields": fields_payload,
        "warnings": res["warnings"],
        "fallback_paste_file": str(paste_file),
        "after_submit_command": confirm_cmd,
        "after_human_submit_command": confirm_cmd,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    _parse_date(args.date)
    data_dir = Path(args.data_dir)
    log_csv = data_dir / "logbook.csv"
    met_csv = data_dir / "ops_metrics.csv"
    mode = getattr(args, "mode", "human") or "human"
    target_status = "AUTO_SUBMITTED" if mode == "auto" else "SUBMITTED_BY_HUMAN"
    default_note = "Confirmed auto submit" if mode == "auto" else "Confirmed human submit"

    log_rows = _read_csv_rows(log_csv)
    found = False
    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    for r in log_rows:
        if r.get("date") == args.date:
            r["status"] = target_status
            r["updated_at"] = now_iso
            found = True
            break
    if not found:
        print(json.dumps({"ok": False, "error": f"Date {args.date} not found in {log_csv}"}))
        return 1
    _write_csv_rows(log_csv, LOGBOOK_FIELDS, log_rows)

    met_rows = _read_csv_rows(met_csv)
    baseline = float(args.baseline_minutes)
    actual = float(args.actual_minutes)
    saved = round(baseline - actual, 2)
    updated_met = [r for r in met_rows if r.get("date") != args.date]
    updated_met.append(
        {
            "date": args.date,
            "baseline_minutes": baseline,
            "actual_minutes": actual,
            "saved_minutes": saved,
            "status": target_status,
            "mentor_revisions": int(args.revisions),
            "notes": args.note or default_note,
        }
    )
    updated_met.sort(key=lambda r: r.get("date", ""))
    _write_csv_rows(met_csv, METRICS_FIELDS, updated_met)

    print(
        json.dumps(
            {
                "ok": True,
                "date": args.date,
                "status": target_status,
                "submit_mode": mode,
                "actual_minutes": actual,
                "saved_minutes": saved,
                "mentor_revisions": int(args.revisions),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def compute_status(data_dir: Path, start_date_str: str, as_of_str: str) -> dict[str, Any]:
    start_d = _parse_date(start_date_str)
    as_of_d = _parse_date(as_of_str)
    log_rows = _read_csv_rows(data_dir / "logbook.csv")
    met_rows = _read_csv_rows(data_dir / "ops_metrics.csv")

    recorded_by_date = {r["date"]: r for r in log_rows if r.get("date")}
    workdays: list[str] = []
    cur = start_d
    while cur <= as_of_d:
        if cur.weekday() < 5:
            workdays.append(cur.isoformat())
        cur += dt.timedelta(days=1)

    missed = [d for d in workdays if d not in recorded_by_date]
    pending = [d for d in workdays if d in recorded_by_date and recorded_by_date[d].get("status") not in SUBMITTED_STATUSES]
    submitted = [d for d in workdays if d in recorded_by_date and recorded_by_date[d].get("status") in SUBMITTED_STATUSES]

    auto_submitted_mins: list[float] = []
    total_saved = 0.0
    total_revisions = 0
    for r in met_rows:
        if r.get("status") not in SUBMITTED_STATUSES:
            continue
        total_revisions += int(r.get("mentor_revisions") or 0)
        if r.get("notes") == "baseline_manual_pre_ops":
            continue
        if r.get("actual_minutes") not in ("", None):
            auto_submitted_mins.append(float(r["actual_minutes"]))
        if r.get("saved_minutes") not in ("", None):
            total_saved += float(r["saved_minutes"])

    median_min = round(statistics.median(auto_submitted_mins), 2) if auto_submitted_mins else None
    usage_rate = round((len(submitted) / len(workdays)) * 100.0, 1) if workdays else 0.0

    if len(auto_submitted_mins) < 5:
        verdict = "TRIAL_IN_PROGRESS"
    elif median_min is not None and median_min <= 4.0 and usage_rate >= 80.0 and total_revisions == 0:
        verdict = "KEEP"
    elif (median_min is not None and median_min > 8.0) or usage_rate < 50.0:
        verdict = "KILL"
    else:
        verdict = "ITERATE"

    return {
        "window_start": start_d.isoformat(),
        "as_of": as_of_d.isoformat(),
        "elapsed_workdays": len(workdays),
        "submitted_days": len(submitted),
        "pending_human_review_days": pending,
        "missed_workdays": missed,
        "automation_runs_measured": len(auto_submitted_mins),
        "median_minutes_per_day": median_min,
        "target_median_minutes": 4.0,
        "total_minutes_saved": round(total_saved, 2),
        "mentor_revisions_total": total_revisions,
        "usage_rate_pct": usage_rate,
        "two_week_verdict": verdict,
    }


def cmd_status(args: argparse.Namespace) -> int:
    as_of = args.as_of or dt.date.today().isoformat()
    start = args.start_date or as_of
    report = compute_status(Path(args.data_dir), start, as_of)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="logbook_ops.py",
        description="Zero-dependency MagangHub Monev daily logbook compiler, Delivery Gate, and compliance tracker.",
    )
    p.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parent.parent / "local-data"),
        help="Directory holding CSV ledger and drafts/ (gitignored)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    col = sub.add_parser("collect", help="Collect daily work evidence from local chats, git commits, and notes")
    col.add_argument("--date", default="", help="Local workday date YYYY-MM-DD (defaults to today)")
    col.add_argument("--repo", action="append", default=[], help="Extra git repository path")
    col.add_argument("--chat-dir", action="append", default=[], help="Override/add chat session directory")
    col.add_argument("--notes", default="", help="Manual work bullets/notes")
    col.add_argument("--notes-file", default="", help="Path to manual notes file")
    col.add_argument("--no-chats", action="store_true", help="Skip chat log scan")
    col.add_argument("--no-git", action="store_true", help="Skip git commit scan")
    col.add_argument("--author", default="", help="Git author filter override")
    col.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms")
    col.add_argument("--redact-confidential", action="store_true", help="Replace confidential terms with [CONFIDENTIAL_CLIENT]")
    col.add_argument("--format", choices=["markdown", "json"], default="markdown")
    col.set_defaults(func=cmd_collect)

    gt = sub.add_parser("gate", help="Run 14-rule Delivery Gate (G-1..G-8) + safety checks")
    gt.add_argument("--json-file", default="", help="JSON draft file with aktivitas/pelajaran/kendala")
    gt.add_argument("--uraian", default="", help="Uraian aktivitas text")
    gt.add_argument("--pembelajaran", default="", help="Pembelajaran yang diperoleh text")
    gt.add_argument("--kendala", default="", help="Kendala yang dialami text")
    gt.add_argument("--raw-notes", default="", help="Raw daily notes to verify numeric tokens against")
    gt.add_argument("--raw-notes-file", default="", help="Path to raw notes file")
    gt.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms")
    gt.add_argument("--no-safety-checks", action="store_true", help="Skip S-1..S-3 safety checks")
    gt.add_argument("--json", action="store_true", help="Emit JSON output")
    gt.set_defaults(func=cmd_gate)

    rec = sub.add_parser("record", help="Validate and record a daily 3-field logbook draft")
    rec.add_argument("--date", required=True, help="Workday ISO date YYYY-MM-DD")
    rec.add_argument("--json-input", default="", help="JSON file containing aktivitas/pelajaran/kendala")
    rec.add_argument("--uraian", default="", help="Uraian aktivitas text")
    rec.add_argument("--pembelajaran", default="", help="Pembelajaran yang diperoleh text")
    rec.add_argument("--kendala", default="", help="Kendala yang dialami text")
    rec.add_argument("--raw-notes", default="", help="Raw daily notes to verify numbers against")
    rec.add_argument("--raw-notes-file", default="", help="Path to raw notes file")
    rec.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms to block")
    rec.add_argument("--skip-delivery-gate", action="store_true", help="Skip G-1..G-8 style gate checks (safety rules remain active)")
    rec.add_argument("--status", default="DRAFT_PENDING_HUMAN_SUBMIT", choices=["DRAFT_PENDING_HUMAN_SUBMIT", "SUBMITTED_BY_HUMAN", "AUTO_SUBMITTED"])
    rec.add_argument("--baseline-minutes", type=float, default=BASELINE_MINUTES_DEFAULT)
    rec.add_argument("--actual-minutes", type=float, default=None)
    rec.add_argument("--revisions", type=int, default=0)
    rec.add_argument("--metric-note", default="")
    rec.add_argument("--allow-warnings", action="store_true", help="Allow saving when non-fatal warnings exist")
    rec.add_argument("--force-overwrite-confirmed", action="store_true", help="Explicitly confirm overwriting an existing date")
    rec.set_defaults(func=cmd_record)

    pf = sub.add_parser("prepare-fill", help="Emit validated Monev browser fill/submit payload (auto-submit default; --draft-only stops before submit)")
    pf.add_argument("--date", required=True, help="Workday ISO date YYYY-MM-DD")
    pf.add_argument("--json-file", default="", help="Optional JSON draft override instead of reading logbook.csv")
    pf.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms")
    pf.add_argument("--draft-only", action="store_true", help="Stop before ticking the confirmation checkbox and clicking Simpan dan Kirim")
    pf.add_argument("--strict-warnings", action="store_true", help="Block prepare-fill when non-fatal warnings exist")
    pf.set_defaults(func=cmd_prepare_fill)

    conf = sub.add_parser("confirm", help="Mark a drafted date as submitted (SUBMITTED_BY_HUMAN or AUTO_SUBMITTED) and log actual minutes")
    conf.add_argument("--date", required=True, help="Workday ISO date YYYY-MM-DD")
    conf.add_argument("--actual-minutes", type=float, required=True, help="Actual end-to-end minutes taken")
    conf.add_argument("--baseline-minutes", type=float, default=BASELINE_MINUTES_DEFAULT)
    conf.add_argument("--revisions", type=int, default=0, help="Mentor revision count (0 if approved cleanly)")
    conf.add_argument("--mode", choices=["human", "auto"], default="human", help="Submission mode: human (SUBMITTED_BY_HUMAN) or auto (AUTO_SUBMITTED)")
    conf.add_argument("--note", default="")
    conf.set_defaults(func=cmd_confirm)

    st = sub.add_parser("status", help="Show missed workdays and 2-week evaluation metric")
    st.add_argument("--start-date", default="", help="Internship start date YYYY-MM-DD (defaults to --as-of/today)")
    st.add_argument("--as-of", default="", help="Evaluation date YYYY-MM-DD (defaults to today)")
    st.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
