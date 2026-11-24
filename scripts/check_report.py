#!/usr/bin/env python3
"""Delivery Gate + safety checks for MagangHub daily reports.

Enforces the 14 Indonesian writing rules (W-01..W-50 / G-1..G-8) adapted
from raditsoic/maganghub-autofill (MIT) along with credential, optional
occupational-safety/authority boundary, and custom NDA term guardrails.
Pure Python 3.9+ stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MIN_CHARS = 100
MAX_CHARS = 5000

FIRST_PERSON = re.compile(r"\b(saya|aku|kami|kita|penulis|gue|gua|gw)\b", re.IGNORECASE)
META = re.compile(
    r"\[INFERENCE|\bcatatan\s*:|\bperlu konfirmasi\b|\banda\b|\bsilakan\b|\bsemoga\b",
    re.IGNORECASE,
)
EM_DASH = re.compile(r"—|\s--\s")

CLICHES = [
    "pengalaman berharga",
    "sangat bermanfaat",
    "luar biasa",
    "di era modern",
    "di era digital",
    "tidak hanya",
    "sebuah perjalanan",
    "membuka wawasan",
    "semakin meningkat",
    "berhasil sempurna",
    "seluruh bug teratasi",
    "performa meningkat drastis",
]

# Nouns/loanwords starting with "di" that are not Indonesian passive verbs.
DI_NOT_PASSIVE = {
    "digital",
    "diagram",
    "dinas",
    "disk",
    "diskusi",
    "dimensi",
    "direktori",
    "distribusi",
    "dinamis",
    "diagnosa",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SECRET_PASSWORD", re.compile(r"\b(?:password|passwd|kata\s+sandi)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("SECRET_API_KEY", re.compile(r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("SECRET_TOKEN_PREFIX", re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{16,})")),
    ("SECRET_OTP", re.compile(r"\b(?:otp|kode\s+verifikasi)\s*[:=]\s*\d{4,8}\b", re.IGNORECASE)),
]

SAFETY_BOUNDARY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "UNSUPERVISED_SAFETY_BOUNDARY",
        re.compile(
            r"\b(?:tanpa\s+(?:loto|izin|pengawasan|mentor|pembimbing|supervisor)|"
            r"bypass\s+proteksi|energize\s+sendiri|switching\s+sendiri|"
            r"manuver\s+tegangan\s+tinggi\s+mandiri)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "INTERN_SOLE_AUTHORITY_CLAIM",
        re.compile(
            r"\b(?:menandatangani\s+slo|mengeluarkan\s+slo|otorisasi\s+tunggal|"
            r"mengesahkan\s+spesifikasi\s+final|memutuskan\s+spesifikasi\s+final\s+sendiri|"
            r"menyetujui\s+pengadaan\s+sendiri)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "UNSUBSTANTIATED_ABSOLUTE_CLAIM",
        re.compile(
            r"\b(?:100%\s+bebas\s+(?:bug|gangguan|kesalahan)|zero\s+failure\s+permanen|"
            r"dijamin\s+aman\s+mutlak)\b",
            re.IGNORECASE,
        ),
    ),
]


def compile_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    prefix = r"(?<!\w)" if term and term[0].isalnum() else ""
    suffix = r"(?!\w)" if term and term[-1].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)


def normalize_report_fields(data: dict[str, Any]) -> dict[str, str]:
    aktivitas = str(data.get("aktivitas") or data.get("uraian_aktivitas") or "").replace("\r\n", "\n").strip()
    pelajaran = str(data.get("pelajaran") or data.get("pembelajaran") or "").replace("\r\n", "\n").strip()
    kendala = str(data.get("kendala") or "").replace("\r\n", "\n").strip()
    return {
        "aktivitas": aktivitas,
        "pelajaran": pelajaran,
        "kendala": kendala,
    }


def evaluate_report(
    data: dict[str, Any],
    *,
    safety_checks: bool = True,
    sensitive_terms: list[str] | None = None,
) -> dict[str, Any]:
    fields = normalize_report_fields(data)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, ok: bool, message: str) -> None:
        checks.append({"id": check_id, "ok": ok, "message": message})

    for name, text in fields.items():
        n = len(text)
        ok = MIN_CHARS <= n <= MAX_CHARS
        add("G-1", ok, f"G-1 {name}: {n} chars (min {MIN_CHARS}, max {MAX_CHARS})")

    joined = "\n".join(fields.values())

    m = FIRST_PERSON.search(joined)
    add("G-2", not m, "G-2 no person pronouns" + (f": found '{m.group(0)}'" if m else ""))

    m = META.search(joined)
    add("G-3", not m, "G-3 no meta tags/notes" + (f": found '{m.group(0)}'" if m else ""))

    m = EM_DASH.search(joined)
    add("G-4", not m, "G-4 no em dash" + (f": found '{m.group(0).strip()}'" if m else ""))

    lines = [line for line in fields["aktivitas"].splitlines() if line.strip()]
    bullets = [line for line in lines if line.lstrip().startswith("- ")]
    g5_ok = bool(lines) and len(bullets) == len(lines) and 3 <= len(lines) <= 5
    add(
        "G-5",
        g5_ok,
        f"G-5 aktivitas: {len(bullets)}/{len(lines)} lines start with '- ' (need 3-5 lines, all bulleted)",
    )

    passive: list[str] = []
    for bullet in bullets:
        cleaned = re.sub(r"^[-\s]+", "", bullet).strip()
        first_token = cleaned.split()[0].lower() if cleaned else ""
        word = re.sub(r"[^a-z]", "", first_token)
        if re.fullmatch(r"di[a-z]{3,}", word) and word not in DI_NOT_PASSIVE:
            passive.append(word)
    add(
        "G-8",
        not passive,
        "G-8 activities open with active meN- verbs" + (f": passive found {', '.join(passive)}" if passive else ""),
    )

    for name in ("pelajaran", "kendala"):
        text = fields[name]
        ok = bool(text) and "\n" not in text and not text.lstrip().startswith(("-", "*"))
        add("G-6", ok, f"G-6 {name}: one paragraph, no bullets")

    lowered = joined.lower()
    found_cliches = [c for c in CLICHES if c in lowered]
    add("G-7", not found_cliches, "G-7 no empty cliches" + (f": {', '.join(found_cliches)}" if found_cliches else ""))

    if safety_checks:
        secret_hits = [code for code, pat in SECRET_PATTERNS if pat.search(joined)]
        add("S-1", not secret_hits, "S-1 no credentials/secrets" + (f": {', '.join(secret_hits)}" if secret_hits else ""))

        boundary_hits = [code for code, pat in SAFETY_BOUNDARY_RULES if pat.search(joined)]
        add(
            "S-2",
            not boundary_hits,
            "S-2 safety/authority boundaries respected" + (f": {', '.join(boundary_hits)}" if boundary_hits else ""),
        )

        terms = [t.strip() for t in (sensitive_terms or []) if t.strip()]
        if terms:
            leaked_terms = [t for t in terms if compile_term_pattern(t).search(joined)]
            add(
                "S-3",
                not leaked_terms,
                "S-3 no confidential terms" + (f": {', '.join(leaked_terms)}" if leaked_terms else ""),
            )

    passed_count = sum(1 for c in checks if c["ok"])
    failed_checks = [c for c in checks if not c["ok"]]
    return {
        "ok": len(failed_checks) == 0,
        "passed": passed_count,
        "total": len(checks),
        "char_counts": {k: len(v) for k, v in fields.items()},
        "checks": checks,
        "failed_checks": failed_checks,
    }


def _load_json_input(path_arg: str | None) -> dict[str, Any]:
    if path_arg:
        with Path(path_arg).open("r", encoding="utf-8") as f:
            return json.load(f)
    return json.load(sys.stdin)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delivery Gate & safety validator for MagangHub daily reports.")
    parser.add_argument("report_json", nargs="?", help="Path to JSON file (omit to read from stdin)")
    parser.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms to block")
    parser.add_argument("--no-safety-checks", action="store_true", help="Skip S-1..S-3 safety checks (run G-1..G-8 only)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    data = _load_json_input(args.report_json)
    extra_terms = [t.strip() for t in args.sensitive_terms.split(",") if t.strip()]
    result = evaluate_report(
        data,
        safety_checks=not args.no_safety_checks,
        sensitive_terms=extra_terms,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for c in result["checks"]:
            print(("PASS " if c["ok"] else "FAIL ") + c["message"])
        status = "PASS" if result["ok"] else "FAIL"
        print(f"\n{status}: {result['passed']}/{result['total']} checks passed")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
