#!/usr/bin/env python3
"""Zero-dependency Excel (.xlsx) & CSV converter for MagangHub iOS Safari tools.

Pure Python 3.9+ standard library only (no openpyxl or pandas). Reads .xlsx via
zipfile + xml.etree.ElementTree or delimited .csv/.tsv files, normalizes dates
to YYYY-MM-DD, enforces the 14-rule Delivery Gate + secret/NDA checks + 3-day
Jaccard duplicate-drift detection, and outputs JSON plus optional preloaded
iOS Shortcuts JS or Safari Userscript files.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = REPO_ROOT / "skills" / "maganghub-logbook-ops" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

import check_report as gate

DUPLICATE_JACCARD_THRESHOLD = 0.65
WORD_RE = re.compile(r"[a-z0-9]{4,}", re.IGNORECASE)
STOPWORDS = {
    "yang", "untuk", "dengan", "pada", "dari", "agar", "juga",
    "dalam", "serta", "masih", "perlu", "saat", "oleh", "atau", "akan",
    "telah", "harus", "tidak", "bisa", "dapat", "tiap", "setiap",
}

HEADER_ALIASES: dict[str, set[str]] = {
    "date": {
        "date", "tanggal", "tgl", "hari tanggal", "hari tgl",
        "tanggal laporan", "iso date",
    },
    "aktivitas": {
        "aktivitas", "uraian aktivitas", "kegiatan", "uraian kegiatan",
        "aktivitas harian",
    },
    "pelajaran": {
        "pelajaran", "pembelajaran", "pembelajaran yang diperoleh",
        "ilmu pembelajaran", "ilmu yang diperoleh",
    },
    "kendala": {
        "kendala", "kendala yang dialami", "hambatan", "kendala hambatan",
    },
}

MONTH_MAP: dict[str, int] = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "pebruari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "nop": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}

WEEKDAY_PREFIX_RE = re.compile(
    r"^(?:senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*",
    re.IGNORECASE,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _norm_header(text: str) -> str:
    return re.sub(r"[\s_/-]+", " ", text.strip().lower()).strip()


def _col_letters_to_index(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _extract_xml_text(elem: ET.Element) -> str:
    parts: list[str] = []

    def walk(node: ET.Element) -> None:
        name = _local_name(node.tag)
        if name == "rPh":
            return
        if name == "t" and node.text:
            parts.append(node.text)
        for child in node:
            walk(child)

    walk(elem)
    return "".join(parts)


def _resolve_xlsx_sheet_target(
    zf: zipfile.ZipFile,
    sheet_name: str | None,
) -> tuple[str, bool]:
    names = set(zf.namelist())
    use_1904 = False
    sheets: list[tuple[str, str]] = []

    if "xl/workbook.xml" in names:
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        for el in wb_root.iter():
            lname = _local_name(el.tag)
            if lname == "workbookPr":
                if el.attrib.get("date1904", "").lower() in {"1", "true"}:
                    use_1904 = True
            elif lname == "sheet":
                name = el.attrib.get("name", "")
                rid = ""
                for k, v in el.attrib.items():
                    if _local_name(k) == "id":
                        rid = v
                        break
                if name:
                    sheets.append((name, rid))

    rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for el in rels_root.iter():
            if _local_name(el.tag) == "Relationship":
                rid = el.attrib.get("Id", "")
                target = el.attrib.get("Target", "")
                if rid and target:
                    if target.startswith("/"):
                        resolved = target.lstrip("/")
                    elif target.startswith("xl/"):
                        resolved = target
                    else:
                        resolved = posixpath.normpath(f"xl/{target}")
                    rels[rid] = resolved

    if sheet_name:
        exact = [(n, rid) for n, rid in sheets if n == sheet_name]
        ci = [(n, rid) for n, rid in sheets if n.lower() == sheet_name.lower()]
        chosen = exact[0] if exact else (ci[0] if ci else None)
        if not chosen:
            available = ", ".join(n for n, _ in sheets) or "(none)"
            raise ValueError(f"Sheet '{sheet_name}' not found. Available sheets: {available}")
        target = rels.get(chosen[1], "")
        if target and target in names:
            return target, use_1904
        raise ValueError(f"Worksheet target for '{sheet_name}' missing inside .xlsx archive.")

    if sheets:
        first_target = rels.get(sheets[0][1], "")
        if first_target and first_target in names:
            return first_target, use_1904

    if "xl/worksheets/sheet1.xml" in names:
        return "xl/worksheets/sheet1.xml", use_1904
    candidates = sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if candidates:
        return candidates[0], use_1904
    raise ValueError("No worksheet XML found inside .xlsx archive.")


def read_xlsx_rows(path: Path, *, sheet_name: str | None = None) -> tuple[list[list[str]], bool]:
    """Read non-empty worksheet rows from an .xlsx file using pure stdlib."""
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for el in ss_root.iter():
                if _local_name(el.tag) == "si":
                    shared_strings.append(_extract_xml_text(el))

        target_xml, use_1904 = _resolve_xlsx_sheet_target(zf, sheet_name)
        ws_root = ET.fromstring(zf.read(target_xml))

        rows: list[list[str]] = []
        for row_el in ws_root.iter():
            if _local_name(row_el.tag) != "row":
                continue
            cell_map: dict[int, str] = {}
            max_col = -1
            next_col = 0
            for cell_el in row_el:
                if _local_name(cell_el.tag) != "c":
                    continue
                ref = cell_el.attrib.get("r", "")
                m = re.match(r"^([A-Za-z]+)", ref)
                col_idx = _col_letters_to_index(m.group(1)) if m else next_col
                next_col = col_idx + 1
                max_col = max(max_col, col_idx)

                ctype = cell_el.attrib.get("t", "")
                val = ""
                if ctype == "inlineStr":
                    for child in cell_el:
                        if _local_name(child.tag) == "is":
                            val = _extract_xml_text(child)
                            break
                else:
                    v_text = ""
                    for child in cell_el:
                        if _local_name(child.tag) == "v" and child.text is not None:
                            v_text = child.text
                            break
                    if ctype == "s":
                        if v_text.strip() != "":
                            idx = int(v_text.strip())
                            val = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                    elif ctype == "b":
                        val = "TRUE" if v_text.strip() == "1" else "FALSE"
                    else:
                        val = v_text
                cell_map[col_idx] = val

            if max_col < 0:
                continue
            row_vals = [cell_map.get(i, "") for i in range(max_col + 1)]
            if any(str(c).strip() for c in row_vals):
                rows.append(row_vals)
        return rows, use_1904


def _detect_csv_delimiter(text: str, suffix: str) -> str:
    first_line = ""
    for line in text.splitlines():
        if line.strip():
            first_line = line
            break
    if suffix.lower() == ".tsv" and "\t" in first_line:
        return "\t"

    counts: dict[str, int] = {",": 0, ";": 0, "\t": 0}
    in_quotes = False
    for ch in first_line:
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes and ch in counts:
            counts[ch] += 1
    best = max((",", ";", "\t"), key=lambda d: (counts[d], 1 if d == ";" else 0))
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> list[list[str]]:
    """Read delimited rows (.csv/.tsv) with UTF-8 BOM and cp1252 fallback."""
    raw_bytes = path.read_bytes()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("cp1252")
    delim = _detect_csv_delimiter(text, path.suffix)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    return [row for row in reader if any(cell.strip() for cell in row)]


def parse_excel_date(raw_value: str, *, use_1904: bool = False) -> str:
    """Normalize ISO, DMY, Indonesian/English month names, or Excel serial dates."""
    s = raw_value.strip()
    if not s:
        raise ValueError("Empty date cell.")

    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        num = float(s)
        if 30000 <= num <= 65000:
            base = dt.date(1904, 1, 1) if use_1904 else dt.date(1899, 12, 30)
            return (base + dt.timedelta(days=int(math.floor(num)))).isoformat()
        if "." not in s and len(s) == 8 and 19000101 <= int(s) <= 21001231:
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat()

    cleaned = WEEKDAY_PREFIX_RE.sub("", s).strip()

    m_iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s].*)?$", cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return dt.date(y, m, d).isoformat()

    m_dmy = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:\s.*)?$", cleaned)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        return dt.date(y, m, d).isoformat()

    m_named = re.match(r"^(\d{1,2})[\s-]+([A-Za-z]+)[\s,-]+(\d{4})(?:\s.*)?$", cleaned)
    if m_named:
        d = int(m_named.group(1))
        mon_key = m_named.group(2).lower().rstrip(".")
        y = int(m_named.group(3))
        if mon_key not in MONTH_MAP:
            raise ValueError(f"Unknown month name '{m_named.group(2)}' in date: {raw_value!r}")
        return dt.date(y, MONTH_MAP[mon_key], d).isoformat()

    m_mdy_named = re.match(r"^([A-Za-z]+)[\s-]+(\d{1,2})[\s,]+(\d{4})(?:\s.*)?$", cleaned)
    if m_mdy_named:
        mon_key = m_mdy_named.group(1).lower().rstrip(".")
        d = int(m_mdy_named.group(2))
        y = int(m_mdy_named.group(3))
        if mon_key not in MONTH_MAP:
            raise ValueError(f"Unknown month name '{m_mdy_named.group(1)}' in date: {raw_value!r}")
        return dt.date(y, MONTH_MAP[mon_key], d).isoformat()

    raise ValueError(f"Unrecognized date format: {raw_value!r}")


def _resolve_col_override(header_row: list[str], spec: str) -> int | None:
    target = spec.strip()
    if not target:
        return None
    target_norm = _norm_header(target)
    for idx, cell in enumerate(header_row):
        if cell.strip().lower() == target.lower() or _norm_header(cell) == target_norm:
            return idx
    if target.isdigit():
        one_based = int(target)
        if 1 <= one_based <= len(header_row):
            return one_based - 1
    if re.fullmatch(r"[A-Za-z]{1,2}", target):
        idx = _col_letters_to_index(target)
        if 0 <= idx < len(header_row):
            return idx
    return None


def _match_header_row(
    rows: list[list[str]],
    overrides: dict[str, str],
) -> tuple[int, dict[str, int]]:
    scan_limit = min(len(rows), 10)
    for r_idx in range(scan_limit):
        row = rows[r_idx]
        mapping: dict[str, int] = {}
        for field, override in overrides.items():
            if override:
                col_idx = _resolve_col_override(row, override)
                if col_idx is not None:
                    mapping[field] = col_idx
                continue
            for idx, cell in enumerate(row):
                if _norm_header(cell) in HEADER_ALIASES[field]:
                    mapping[field] = idx
                    break
        if len(mapping) == 4:
            return r_idx, mapping
    raise ValueError(
        "Could not locate required 4 header columns (date/tanggal, aktivitas, pelajaran, kendala) "
        "in the first 10 rows. Pass --date-col/--aktivitas-col/--pelajaran-col/--kendala-col."
    )


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text) if w.lower() not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def convert_and_validate(
    input_path: Path,
    *,
    sheet_name: str | None = None,
    col_overrides: dict[str, str] | None = None,
    sensitive_terms: list[str] | None = None,
    no_gate: bool = False,
    skip_invalid: bool = False,
) -> dict[str, Any]:
    """Read .xlsx/.csv/.tsv, validate every row, and compute 3-day Jaccard drift."""
    suffix = input_path.suffix.lower()
    use_1904 = False
    if suffix == ".xlsx":
        rows, use_1904 = read_xlsx_rows(input_path, sheet_name=sheet_name)
    elif suffix in {".csv", ".tsv"}:
        rows = read_csv_rows(input_path)
    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Use .xlsx, .csv, or .tsv.")

    if not rows:
        raise ValueError("Input file has no non-empty rows.")

    overrides = col_overrides or {"date": "", "aktivitas": "", "pelajaran": "", "kendala": ""}
    header_idx, col_map = _match_header_row(rows, overrides)

    entries: dict[str, dict[str, str]] = {}
    rejected: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    terms = [t.strip() for t in (sensitive_terms or []) if t.strip()]

    for raw_row_num, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        def cell_at(field: str) -> str:
            idx = col_map[field]
            return row[idx].replace("\r\n", "\n").strip() if idx < len(row) else ""

        raw_date = cell_at("date")
        aktivitas = cell_at("aktivitas")
        pelajaran = cell_at("pelajaran")
        kendala = cell_at("kendala")

        if not (raw_date or aktivitas or pelajaran or kendala):
            continue

        row_errors: list[str] = []
        iso_date = raw_date or f"row-{raw_row_num}"
        try:
            iso_date = parse_excel_date(raw_date, use_1904=use_1904)
        except ValueError as exc:
            row_errors.append(f"INVALID_DATE:{exc}")

        if not row_errors and iso_date in seen_dates:
            row_errors.append(f"DUPLICATE_DATE:{iso_date}")
        elif not row_errors:
            seen_dates.add(iso_date)

        fields = {
            "aktivitas": aktivitas,
            "pelajaran": pelajaran,
            "kendala": kendala,
        }

        if no_gate:
            for name, val in fields.items():
                if not val:
                    row_errors.append(f"EMPTY_FIELD:{name}")
            joined = "\n".join(fields.values())
            for code, pat in gate.SECRET_PATTERNS:
                if pat.search(joined):
                    row_errors.append(f"S-1:CREDENTIAL_LEAK_BLOCKED:{code}")
            for code, pat in gate.SAFETY_BOUNDARY_RULES:
                if pat.search(joined):
                    row_errors.append(f"S-2:CLAIM_BOUNDARY_VIOLATION:{code}")
            for term in terms:
                if gate.compile_term_pattern(term).search(joined):
                    row_errors.append(f"S-3:SENSITIVE_TERM_LEAK:{term}")
        else:
            res = gate.evaluate_report(fields, safety_checks=True, sensitive_terms=terms)
            for chk in res["failed_checks"]:
                row_errors.append(f"{chk['id']}:{chk['message']}")

        if row_errors:
            rejected.append({
                "row": raw_row_num,
                "date": iso_date,
                "errors": row_errors,
            })
            continue

        entries[iso_date] = fields

    sorted_dates = sorted(entries.keys())
    sorted_entries = {d: entries[d] for d in sorted_dates}

    word_cache = {
        d: _content_words(
            " ".join([sorted_entries[d]["aktivitas"], sorted_entries[d]["pelajaran"], sorted_entries[d]["kendala"]])
        )
        for d in sorted_dates
    }
    for idx, d in enumerate(sorted_dates):
        for prev_d in sorted_dates[max(0, idx - 3):idx]:
            sim = _jaccard(word_cache[d], word_cache[prev_d])
            if sim >= DUPLICATE_JACCARD_THRESHOLD:
                warnings.append({
                    "date": d,
                    "compared_with": prev_d,
                    "jaccard": round(sim, 2),
                    "code": "DUPLICATE_DRIFT_ALERT",
                    "message": f"Jaccard similarity {sim:.2f} with {prev_d} (>= {DUPLICATE_JACCARD_THRESHOLD})",
                })

    ok = len(rejected) == 0 or (skip_invalid and len(sorted_entries) > 0)
    return {
        "ok": ok,
        "source": str(input_path),
        "entry_count": len(sorted_entries),
        "rejected_count": len(rejected),
        "warning_count": len(warnings),
        "rejected": rejected,
        "warnings": warnings,
        "payload": {
            "schema_version": 1,
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "entry_count": len(sorted_entries),
            "entries": sorted_entries,
        },
    }


def _inject_template(
    template_path: Path,
    payload: dict[str, Any],
    *,
    auto_submit: bool,
) -> str:
    text = template_path.read_text(encoding="utf-8")
    auto_val = "true" if auto_submit else "false"
    text, n_auto = re.subn(
        r"/\*\s*__MAGANGHUB_AUTO_SUBMIT__\s*\*/\s*(?:true|false)",
        f"/* __MAGANGHUB_AUTO_SUBMIT__ */ {auto_val}",
        text,
        count=1,
    )
    if n_auto != 1:
        raise ValueError(f"Template {template_path.name} missing __MAGANGHUB_AUTO_SUBMIT__ marker.")

    safe_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    pattern_json = re.compile(
        r"/\*\s*__MAGANGHUB_LOGBOOKS_JSON__\s*\*/[\s\S]*?/\*\s*__MAGANGHUB_LOGBOOKS_JSON_END__\s*\*/"
    )
    replacement = f"/* __MAGANGHUB_LOGBOOKS_JSON__ */ {safe_json} /* __MAGANGHUB_LOGBOOKS_JSON_END__ */"
    text, n_json = pattern_json.subn(lambda _m: replacement, text, count=1)
    if n_json != 1:
        raise ValueError(f"Template {template_path.name} missing __MAGANGHUB_LOGBOOKS_JSON__ markers.")
    return text


def write_sample_csv(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ["tanggal", "aktivitas", "pelajaran", "kendala"],
        [
            "2026-11-25",
            "- Mengaudit endpoint autentikasi pada layanan backend menggunakan skrip pengujian otomatis untuk memverifikasi masa berlaku token sesi dan respons kode error.\n"
            "- Memperbaiki validasi skema payload permintaan pada modul manajemen pengguna agar input karakter khusus tidak memicu kegagalan parsing JSON.\n"
            "- Menjalankan ulang rangkaian unit test dan integration test pada modul otorisasi guna memastikan tidak ada regresi setelah pembaruan validator.",
            "Pengujian batas tepi pada validasi payload API dan masa kedaluwarsa token autentikasi membantu mencegah celah kesalahan parsing sebelum kode digabungkan ke cabang utama. Penerapan pemeriksaan input lebih awal pada lapisan skema juga memperjelas pesan galat bagi pengembang frontend saat melakukan integrasi.",
            "Dokumentasi contoh respons galat untuk skenario token kedaluwarsa di lingkungan staging belum seragam antar layanan sehingga memerlukan verifikasi langsung ke log server bersama pembimbing. Keterbatasan data uji akun dengan peran terbatas juga sempat memperlambat pengujian skenario penolakan akses.",
        ],
        [
            "2026-11-26",
            "- Menyusun skenario pengujian antarmuka responsif pada perangkat seluler untuk halaman formulir pelaporan harian dan ringkasan riwayat.\n"
            "- Mengevaluasi performa kueri basis data pada halaman daftar riwayat menggunakan indeks komposit tanggal dan status persetujuan agar waktu muat lebih singkat.\n"
            "- Mendokumentasikan temuan ketidaksesuaian tata letak tombol konfirmasi pada layar sempit ke dalam pelacak isu tim untuk ditindaklanjuti pada sprint berikutnya.",
            "Optimasi indeks komposit pada kolom tanggal dan status mampu menurunkan latensi pembacaan tabel riwayat secara nyata tanpa mengubah struktur aplikasi yang sudah berjalan. Evaluasi tampilan pada lebar layar ponsel juga menunjukkan pentingnya penempatan tombol aksi utama agar tetap terlihat tanpa perlu gulir berlebih.",
            "Perangkat uji fisik berukuran layar kecil belum tersedia di meja kerja sehingga verifikasi tata letak hanya dapat dilakukan melalui mode emulasi peramban sambil menunggu jadwal peminjaman unit uji dari tim QA.",
        ],
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="excel_to_ios_json.py",
        description="Convert Excel (.xlsx) or CSV/TSV internship logs to validated JSON + iOS Safari scripts (stdlib only).",
    )
    p.add_argument("input_file", nargs="?", default="", help="Path to .xlsx, .csv, or .tsv file")
    p.add_argument("--sheet", default="", help="Worksheet name for .xlsx (defaults to first sheet)")
    p.add_argument("--date-col", default="", help="Override date column name or 1-based index")
    p.add_argument("--aktivitas-col", default="", help="Override aktivitas column name or 1-based index")
    p.add_argument("--pelajaran-col", default="", help="Override pelajaran column name or 1-based index")
    p.add_argument("--kendala-col", default="", help="Override kendala column name or 1-based index")
    p.add_argument("--sensitive-terms", default="", help="Comma-separated confidential terms to block")
    p.add_argument("--no-gate", action="store_true", help="Skip G-1..G-8 style checks (S-1..S-3 safety/secret checks stay active)")
    p.add_argument("--skip-invalid", action="store_true", help="Skip failing rows instead of aborting output")
    p.add_argument("--out", default="logbooks.json", help="Output JSON path (default: logbooks.json)")
    p.add_argument("--emit-shortcut-js", default="", help="Optional output path for preloaded iOS Shortcut JS")
    p.add_argument("--emit-userscript", default="", help="Optional output path for preloaded Safari Userscript (.user.js)")
    p.add_argument("--draft-only", action="store_true", help="Set autoSubmit=false in emitted JS/userscript files")
    p.add_argument("--write-sample-csv", default="", help="Write a 2-row generic sample CSV to this path and exit if no input_file")
    p.add_argument("--json", action="store_true", help="Print JSON summary report")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.write_sample_csv:
        sample_out = Path(args.write_sample_csv)
        write_sample_csv(sample_out)
        if not args.input_file:
            if args.json:
                print(json.dumps({"ok": True, "sample_csv": str(sample_out)}, ensure_ascii=False, indent=2))
            else:
                print(f"Wrote sample CSV template to {sample_out}")
            return 0

    if not args.input_file:
        parser.error("Provide input_file (.xlsx/.csv/.tsv) or --write-sample-csv <path>.")

    input_path = Path(args.input_file)
    if not input_path.is_file():
        print(json.dumps({"ok": False, "error": f"Input file not found: {input_path}"}), file=sys.stderr)
        return 2

    terms = [t.strip() for t in args.sensitive_terms.split(",") if t.strip()]
    overrides = {
        "date": args.date_col,
        "aktivitas": args.aktivitas_col,
        "pelajaran": args.pelajaran_col,
        "kendala": args.kendala_col,
    }
    try:
        report = convert_and_validate(
            input_path,
            sheet_name=args.sheet or None,
            col_overrides=overrides,
            sensitive_terms=terms,
            no_gate=args.no_gate,
            skip_invalid=args.skip_invalid,
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not report["ok"]:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for rej in report["rejected"]:
                print(f"FAIL row {rej['row']} ({rej['date']}): " + "; ".join(rej["errors"]), file=sys.stderr)
            print(f"Blocked export: {report['rejected_count']} failing row(s). Pass --skip-invalid to omit failing rows.", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report["payload"], ensure_ascii=False, indent=2), encoding="utf-8")
    report["output_json"] = str(out_path)

    here = Path(__file__).resolve().parent
    auto_submit = not args.draft_only

    if args.emit_shortcut_js:
        js_out = Path(args.emit_shortcut_js)
        js_out.parent.mkdir(parents=True, exist_ok=True)
        rendered_js = _inject_template(here / "ios_shortcut_fill.js", report["payload"], auto_submit=auto_submit)
        js_out.write_text(rendered_js, encoding="utf-8")
        report["output_shortcut_js"] = str(js_out)

    if args.emit_userscript:
        us_out = Path(args.emit_userscript)
        us_out.parent.mkdir(parents=True, exist_ok=True)
        rendered_us = _inject_template(here / "safari_userscript.user.js", report["payload"], auto_submit=auto_submit)
        us_out.write_text(rendered_us, encoding="utf-8")
        report["output_userscript"] = str(us_out)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"OK: exported {report['entry_count']} entries -> {out_path}")
        if report["rejected_count"]:
            print(f"SKIPPED: {report['rejected_count']} invalid row(s).")
        for w in report["warnings"]:
            print(f"WARN [{w['code']}] {w['date']}: {w['message']}")
        if "output_shortcut_js" in report:
            print(f"SHORTCUT JS: {report['output_shortcut_js']} (autoSubmit={auto_submit})")
        if "output_userscript" in report:
            print(f"USERSCRIPT: {report['output_userscript']} (autoSubmit={auto_submit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
