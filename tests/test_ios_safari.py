"""Unit tests for the pure-stdlib iOS Safari / Shortcuts companion toolkit."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
IOS_DIR = REPO_ROOT / "ios-safari"
SKILL_SCRIPTS = REPO_ROOT / "skills" / "maganghub-logbook-ops" / "scripts"
for p in (IOS_DIR, SKILL_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import check_report as gate
import excel_to_ios_json as conv


def _build_minimal_xlsx(
    out_path: Path,
    *,
    sheets: dict[str, list[dict[str, tuple[str, str]]]],
    shared_strings: list[str] | None = None,
    rich_shared_idx: dict[int, list[str]] | None = None,
    use_1904: bool = False,
) -> None:
    """Create a real OOXML .xlsx zip package in temp dir using stdlib only."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    sheet_names = list(sheets.keys())
    wb_sheets_xml = "".join(
        f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, name in enumerate(sheet_names, start=1)
    )
    wb_pr = '<workbookPr date1904="1"/>' if use_1904 else '<workbookPr/>'
    workbook_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{ns}" xmlns:r="{r_ns}">'
        f'{wb_pr}<sheets>{wb_sheets_xml}</sheets></workbook>'
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{idx}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
            for idx in range(1, len(sheet_names) + 1)
        )
        + "</Relationships>"
    )

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)

        if shared_strings is not None or rich_shared_idx is not None:
            si_items: list[str] = []
            ss_list = shared_strings or []
            for idx, val in enumerate(ss_list):
                if rich_shared_idx and idx in rich_shared_idx:
                    runs = "".join(f'<r><t xml:space="preserve">{escape(part)}</t></r>' for part in rich_shared_idx[idx])
                    si_items.append(f"<si>{runs}</si>")
                else:
                    si_items.append(f'<si><t xml:space="preserve">{escape(val)}</t></si>')
            ss_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<sst xmlns="{ns}" count="{len(si_items)}" uniqueCount="{len(si_items)}">'
                + "".join(si_items)
                + "</sst>"
            )
            zf.writestr("xl/sharedStrings.xml", ss_xml)

        for idx, name in enumerate(sheet_names, start=1):
            rows_xml: list[str] = []
            for r_num, row_cells in enumerate(sheets[name], start=1):
                cells_xml: list[str] = []
                for col_ref, (ctype, raw_val) in row_cells.items():
                    ref = f"{col_ref}{r_num}"
                    if ctype == "inlineStr":
                        cells_xml.append(
                            f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(raw_val)}</t></is></c>'
                        )
                    elif ctype == "s":
                        cells_xml.append(f'<c r="{ref}" t="s"><v>{escape(raw_val)}</v></c>')
                    else:
                        cells_xml.append(f'<c r="{ref}"><v>{escape(raw_val)}</v></c>')
                rows_xml.append(f'<row r="{r_num}">{"".join(cells_xml)}</row>')
            ws_xml = (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<worksheet xmlns="{ns}"><sheetData>{"".join(rows_xml)}</sheetData></worksheet>'
            )
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", ws_xml)


VALID_DAY_1 = {
    "aktivitas": (
        "- Mengaudit endpoint autentikasi pada layanan backend menggunakan skrip pengujian otomatis untuk memverifikasi masa berlaku token sesi dan respons kode error.\n"
        "- Memperbaiki validasi skema payload permintaan pada modul manajemen pengguna agar input karakter khusus tidak memicu kegagalan parsing JSON.\n"
        "- Menjalankan ulang rangkaian unit test dan integration test pada modul otorisasi guna memastikan tidak ada regresi setelah pembaruan validator."
    ),
    "pelajaran": (
        "Pengujian batas tepi pada validasi payload API dan masa kedaluwarsa token autentikasi membantu mencegah celah kesalahan parsing sebelum kode digabungkan ke cabang utama. "
        "Penerapan pemeriksaan input lebih awal pada lapisan skema juga memperjelas pesan galat bagi pengembang frontend saat melakukan integrasi."
    ),
    "kendala": (
        "Dokumentasi contoh respons galat untuk skenario token kedaluwarsa di lingkungan staging belum seragam antar layanan sehingga memerlukan verifikasi langsung ke log server bersama pembimbing. "
        "Keterbatasan data uji akun dengan peran terbatas juga sempat memperlambat pengujian skenario penolakan akses."
    ),
}

VALID_DAY_2 = {
    "aktivitas": (
        "- Menyusun skenario pengujian antarmuka responsif pada perangkat seluler untuk halaman formulir pelaporan harian dan ringkasan riwayat.\n"
        "- Mengevaluasi performa kueri basis data pada halaman daftar riwayat menggunakan indeks komposit tanggal dan status persetujuan agar waktu muat lebih singkat.\n"
        "- Mendokumentasikan temuan ketidaksesuaian tata letak tombol konfirmasi pada layar sempit ke dalam pelacak isu tim untuk ditindaklanjuti pada sprint berikutnya."
    ),
    "pelajaran": (
        "Optimasi indeks komposit pada kolom tanggal dan status mampu menurunkan latensi pembacaan tabel riwayat secara nyata tanpa mengubah struktur aplikasi yang sudah berjalan. "
        "Evaluasi tampilan pada lebar layar ponsel juga menunjukkan pentingnya penempatan tombol aksi utama agar tetap terlihat tanpa perlu gulir berlebih."
    ),
    "kendala": (
        "Perangkat uji fisik berukuran layar kecil belum tersedia di meja kerja sehingga verifikasi tata letak hanya dapat dilakukan melalui mode emulasi peramban sambil menunggu jadwal peminjaman unit uji dari tim QA."
    ),
}


class TestIOSSafariToolkit(unittest.TestCase):
    def test_sample_logbooks_passes_delivery_gate(self) -> None:
        sample = json.loads((IOS_DIR / "sample_logbooks.json").read_text(encoding="utf-8"))
        self.assertEqual(sample["entry_count"], len(sample["entries"]))
        dates = sorted(sample["entries"].keys())
        for d in dates:
            res = gate.evaluate_report(sample["entries"][d], safety_checks=True)
            self.assertTrue(res["ok"], f"Sample {d} failed gate: {res['failed_checks']}")
        words0 = conv._content_words(" ".join(sample["entries"][dates[0]].values()))
        words1 = conv._content_words(" ".join(sample["entries"][dates[1]].values()))
        self.assertLess(conv._jaccard(words0, words1), conv.DUPLICATE_JACCARD_THRESHOLD)

    def test_xlsx_sparse_rich_text_serial_and_indonesian_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "logs.xlsx"
            shared = [
                "Tanggal",
                "Aktivitas",
                "Pembelajaran",
                "Kendala",
                "Placeholder rich",
                "26 November 2026",
            ]
            rich = {4: [VALID_DAY_1["aktivitas"][:120], VALID_DAY_1["aktivitas"][120:]]}
            # 46351 in 1900 Excel serial calendar = 2026-11-25
            rows_sheet1 = [
                {"A": ("inlineStr", "Catatan"), "B": ("inlineStr", "Rekap Magang")},
                {"A": ("s", "0"), "C": ("s", "1"), "E": ("s", "2"), "F": ("s", "3")},
                {
                    "A": ("n", "46351"),
                    "C": ("s", "4"),
                    "E": ("inlineStr", VALID_DAY_1["pelajaran"]),
                    "F": ("inlineStr", VALID_DAY_1["kendala"]),
                },
                {
                    "A": ("s", "5"),
                    "C": ("inlineStr", VALID_DAY_2["aktivitas"]),
                    "E": ("inlineStr", VALID_DAY_2["pelajaran"]),
                    "F": ("inlineStr", VALID_DAY_2["kendala"]),
                },
            ]
            _build_minimal_xlsx(
                xlsx_path,
                sheets={"Utama": rows_sheet1, "Cadangan": [{"A": ("inlineStr", "ignore")}]},
                shared_strings=shared,
                rich_shared_idx=rich,
            )
            out_json = Path(tmp) / "out.json"
            shortcut_js = Path(tmp) / "shortcut.js"
            userscript_js = Path(tmp) / "script.user.js"

            rc = conv.main([
                str(xlsx_path),
                "--sheet", "Utama",
                "--out", str(out_json),
                "--emit-shortcut-js", str(shortcut_js),
                "--emit-userscript", str(userscript_js),
            ])
            self.assertEqual(rc, 0)

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(sorted(payload["entries"].keys()), ["2026-11-25", "2026-11-26"])
            self.assertEqual(payload["entries"]["2026-11-25"]["aktivitas"], VALID_DAY_1["aktivitas"])

            sc_text = shortcut_js.read_text(encoding="utf-8")
            us_text = userscript_js.read_text(encoding="utf-8")
            self.assertIn("/* __MAGANGHUB_AUTO_SUBMIT__ */ true", sc_text)
            self.assertIn("/* __MAGANGHUB_AUTO_SUBMIT__ */ true", us_text)
            self.assertIn("2026-11-25", sc_text)
            self.assertIn("2026-11-26", us_text)

    def test_xlsx_1904_date_system_and_draft_only_emit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "mac.xlsx"
            # 44889 days after 1904-01-01 = 2026-11-25
            rows = [
                {"A": ("inlineStr", "Date"), "B": ("inlineStr", "Aktivitas"), "C": ("inlineStr", "Pelajaran"), "D": ("inlineStr", "Kendala")},
                {"A": ("n", "44889"), "B": ("inlineStr", VALID_DAY_1["aktivitas"]), "C": ("inlineStr", VALID_DAY_1["pelajaran"]), "D": ("inlineStr", VALID_DAY_1["kendala"])},
            ]
            _build_minimal_xlsx(xlsx_path, sheets={"Sheet1": rows}, use_1904=True)
            out_json = Path(tmp) / "out.json"
            shortcut_js = Path(tmp) / "draft_only.js"

            rc = conv.main([
                str(xlsx_path),
                "--out", str(out_json),
                "--emit-shortcut-js", str(shortcut_js),
                "--draft-only",
            ])
            self.assertEqual(rc, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertIn("2026-11-25", payload["entries"])
            self.assertIn("/* __MAGANGHUB_AUTO_SUBMIT__ */ false", shortcut_js.read_text(encoding="utf-8"))

    def test_semicolon_bom_csv_and_short_indonesian_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "export.csv"
            act_escaped = VALID_DAY_2["aktivitas"].replace('"', '""')
            content = (
                "tanggal;uraian aktivitas;pembelajaran yang diperoleh;kendala yang dialami\n"
                f"27 Des 2026;\"{act_escaped}\";\"{VALID_DAY_2['pelajaran']}\";\"{VALID_DAY_2['kendala']}\"\n"
            )
            csv_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            out_json = Path(tmp) / "csv_out.json"

            rc = conv.main([str(csv_path), "--out", str(out_json)])
            self.assertEqual(rc, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertIn("2026-12-27", payload["entries"])

    def test_fail_closed_gate_sensitive_terms_and_skip_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "mixed.csv"
            bad_act = "- Memperbaiki bug login bersama tim kemarin."
            nda_kendala = VALID_DAY_1["kendala"].replace("layanan", "ClientRahasia")
            rows = [
                "tanggal,aktivitas,pelajaran,kendala",
                f'2026-11-24,"{bad_act}","Terlalu pendek","Masih pendek"',
                f'2026-11-25,"{VALID_DAY_1["aktivitas"]}","{VALID_DAY_1["pelajaran"]}","{nda_kendala}"',
                f'2026-11-26,"{VALID_DAY_2["aktivitas"]}","{VALID_DAY_2["pelajaran"]}","{VALID_DAY_2["kendala"]}"',
            ]
            csv_path.write_text("\n".join(rows), encoding="utf-8")
            out_json = Path(tmp) / "out.json"

            rc_fail = conv.main([str(csv_path), "--sensitive-terms", "ClientRahasia", "--out", str(out_json)])
            self.assertEqual(rc_fail, 1)
            self.assertFalse(out_json.exists())

            rc_skip = conv.main([
                str(csv_path),
                "--sensitive-terms", "ClientRahasia",
                "--skip-invalid",
                "--out", str(out_json),
            ])
            self.assertEqual(rc_skip, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(list(payload["entries"].keys()), ["2026-11-26"])

    def test_no_gate_still_blocks_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "secret.csv"
            # Construct secret token string via parts so static repo scanners are unaffected.
            secret_tok = "sk-" + "ABCDEF1234567890abcd"
            csv_path.write_text(
                "tanggal,aktivitas,pelajaran,kendala\n"
                f'2026-11-25,"- Menguji endpoint memakai {secret_tok}.","Belajar singkat.","Kendala singkat."\n',
                encoding="utf-8",
            )
            out_json = Path(tmp) / "blocked.json"
            rc = conv.main([str(csv_path), "--no-gate", "--out", str(out_json)])
            self.assertEqual(rc, 1)
            self.assertFalse(out_json.exists())

    def test_duplicate_date_and_jaccard_drift_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dup_csv = Path(tmp) / "dup.csv"
            dup_csv.write_text(
                "tanggal,aktivitas,pelajaran,kendala\n"
                f'2026-11-25,"{VALID_DAY_1["aktivitas"]}","{VALID_DAY_1["pelajaran"]}","{VALID_DAY_1["kendala"]}"\n'
                f'2026-11-25,"{VALID_DAY_2["aktivitas"]}","{VALID_DAY_2["pelajaran"]}","{VALID_DAY_2["kendala"]}"\n',
                encoding="utf-8",
            )
            report_dup = conv.convert_and_validate(dup_csv)
            self.assertFalse(report_dup["ok"])
            self.assertTrue(any("DUPLICATE_DATE" in err for err in report_dup["rejected"][0]["errors"]))

            drift_csv = Path(tmp) / "drift.csv"
            drift_csv.write_text(
                "tanggal,aktivitas,pelajaran,kendala\n"
                f'2026-11-25,"{VALID_DAY_1["aktivitas"]}","{VALID_DAY_1["pelajaran"]}","{VALID_DAY_1["kendala"]}"\n'
                f'2026-11-26,"{VALID_DAY_1["aktivitas"]}","{VALID_DAY_1["pelajaran"]}","{VALID_DAY_1["kendala"]}"\n',
                encoding="utf-8",
            )
            report_drift = conv.convert_and_validate(drift_csv)
            self.assertTrue(report_drift["ok"])
            self.assertEqual(report_drift["warning_count"], 1)
            self.assertEqual(report_drift["warnings"][0]["code"], "DUPLICATE_DRIFT_ALERT")

    def test_write_sample_csv_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sample_csv = Path(tmp) / "template.csv"
            rc = conv.main(["--write-sample-csv", str(sample_csv)])
            self.assertEqual(rc, 0)
            self.assertTrue(sample_csv.is_file())
            report = conv.convert_and_validate(sample_csv)
            self.assertTrue(report["ok"])
            self.assertEqual(report["entry_count"], 2)


if __name__ == "__main__":
    unittest.main()
