"""Unit tests for maganghub-logbook-ops public scripts."""

from __future__ import annotations

import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_report as gate
import collect_today as collector
import leak_check as scanner
import logbook_ops as ops

VALID_AKTIVITAS = "\n".join(
    [
        "- Membuat endpoint autentikasi berbasis token pada layanan API beserta skema validasi input.",
        "- Menulis tes unit untuk memverifikasi penanganan token aktif dan token kedaluwarsa secara terpisah.",
        "- Memperbaiki urutan middleware pembaca header permintaan agar token sah tidak ditolak layanan.",
    ]
)
VALID_PELAJARAN = (
    "Pemahaman mengenai alur verifikasi token akses dan pengujian token kedaluwarsa secara terisolasi meningkat. "
    "Urutan pendaftaran middleware pada permintaan HTTP terbukti memengaruhi keberhasilan pembacaan header autentikasi."
)
VALID_KENDALA = (
    "Konfigurasi middleware autentikasi sempat menolak permintaan sah karena dijalankan sebelum middleware pembaca header. "
    "Masalah ditelusuri lewat log permintaan lokal dan diselesaikan dengan menukar urutan keduanya."
)
VALID_RAW = "Buat endpoint API 200 ms, tes unit token 10 kasus, perbaiki urutan middleware 2 file."


class TestCheckReport(unittest.TestCase):
    def test_valid_report_passes_and_di_not_passive(self) -> None:
        akt = "\n".join(
            [
                "- Diskusi desain skema basis data bersama pembimbing untuk modul pelaporan harian.",
                "- Diagram alir layanan autentikasi diselaraskan dengan spesifikasi antarmuka terbaru.",
                "- Menulis pengujian integrasi untuk memastikan respons API sesuai kontrak data.",
            ]
        )
        res = gate.evaluate_report(
            {"aktivitas": akt, "pelajaran": VALID_PELAJARAN, "kendala": VALID_KENDALA},
            sensitive_terms=["SecretClientCo"],
        )
        self.assertTrue(res["ok"], res["failed_checks"])

    def test_rejects_rule_and_safety_violations(self) -> None:
        fake_secret = "sk-" + "Q" * 20
        bad = {
            "aktivitas": "- Dibuat oleh saya di SecretClientCo.\n- Dilakukan tes singkat.",
            "pelajaran": "Pengalaman berharga yang luar biasa — semoga membantu.\n- Baris kedua",
            "kendala": f"Terjadi masalah {fake_secret} tanpa LOTO.",
        }
        res = gate.evaluate_report(bad, sensitive_terms=["SecretClientCo"])
        self.assertFalse(res["ok"])
        failed_ids = {c["id"] for c in res["failed_checks"]}
        self.assertEqual(
            failed_ids,
            {"G-1", "G-2", "G-3", "G-4", "G-5", "G-6", "G-7", "G-8", "S-1", "S-2", "S-3"},
        )


class TestCollectToday(unittest.TestCase):
    def test_iso_date_validation(self) -> None:
        self.assertEqual(collector.parse_iso_date("2026-11-24"), "2026-11-24")
        for bad in ["--upload=evil", "2026-02-30", "yesterday"]:
            with self.assertRaises(ValueError):
                collector.parse_iso_date(bad)

    def test_collect_chats_git_and_redaction(self) -> None:
        today = dt.datetime.now().astimezone().strftime("%Y-%m-%d")
        now_iso = dt.datetime.now().astimezone().isoformat()
        fake_secret = "ghp_" + "B" * 24

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            chat_dir = tmp_path / "chats" / "proj"
            chat_dir.mkdir(parents=True)
            (chat_dir / "log.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "timestamp": now_iso,
                                "cwd": str(tmp_path),
                                "message": {"content": f"Refactor ProjectAlpha with key {fake_secret}"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "user",
                                "timestamp": now_iso,
                                "isMeta": True,
                                "cwd": str(tmp_path),
                                "message": {"content": "Should be skipped"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            repo = tmp_path / "repo"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Demo Intern"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "intern@example.com"], check=True, capture_output=True)
            (repo / "app.py").write_text("print('ok')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "app.py"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "feat: add validator"], check=True, capture_output=True)

            ev = collector.collect_evidence(
                today,
                chat_dirs=[tmp_path / "chats"],
                extra_repos=[repo],
                sensitive_terms=["ProjectAlpha"],
                redact_confidential=True,
                include_cwd=False,
            )
            prompt = ev["chats"][str(tmp_path)][0]["text"]
            self.assertIn("[REDACTED_SECRET]", prompt)
            self.assertNotIn(fake_secret, prompt)
            self.assertIn("[CONFIDENTIAL_CLIENT]", prompt)
            self.assertNotIn("ProjectAlpha", prompt)
            self.assertTrue(any("feat: add validator" in v for v in ev["commits"].values()))


class TestLogbookOpsAndLeakCheck(unittest.TestCase):
    def test_record_prepare_fill_confirm_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            draft_json = tmp_path / "report.json"
            draft_json.write_text(
                json.dumps(
                    {
                        "aktivitas": VALID_AKTIVITAS,
                        "pelajaran": VALID_PELAJARAN,
                        "kendala": VALID_KENDALA,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                ops.main(["--data-dir", tmp, "record", "--date", "2026-11-24", "--json-input", str(draft_json), "--raw-notes", VALID_RAW]),
                0,
            )
            # Duplicate write without confirmation blocked
            self.assertEqual(
                ops.main(["--data-dir", tmp, "record", "--date", "2026-11-24", "--json-input", str(draft_json)]),
                2,
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ops.main(["--data-dir", tmp, "prepare-fill", "--date", "2026-11-24"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["human_in_the_loop_guards"]["tick_confirmation_checkbox"], False)
            self.assertEqual(payload["human_in_the_loop_guards"]["click_simpan_dan_kirim"], False)

            self.assertEqual(
                ops.main(["--data-dir", tmp, "confirm", "--date", "2026-11-24", "--actual-minutes", "3.0", "--revisions", "0"]),
                0,
            )
            # Refuses prepare-fill once submitted
            self.assertEqual(ops.main(["--data-dir", tmp, "prepare-fill", "--date", "2026-11-24"]), 2)

            st = ops.compute_status(tmp_path, "2026-11-24", "2026-11-24")
            self.assertEqual(st["submitted_days"], 1)
            self.assertEqual(st["median_minutes_per_day"], 3.0)

    def test_leak_scanner_flags_pii_paths_secrets_and_blocklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            win_path = "C:\\" + "Users\\" + "sample\\secret.txt"
            personal_mail = "user.person" + "@gmail-demo.org"
            phone = "+628" + "1234567890"
            tok = "sk-" + "T" * 20
            (root / "notes.txt").write_text(
                f"Path: {win_path}\nEmail: {personal_mail}\nPhone: {phone}\nKey: {tok}\nClient: PrivateCorp\n",
                encoding="utf-8",
            )
            (root / "personal.csv").write_text("date,notes\n2026-11-24,ok\n", encoding="utf-8")

            report = scanner.scan_directory(root, blocklist=["PrivateCorp"])
            self.assertFalse(report["ok"])
            rules = {f["rule"] for f in report["findings"]}
            self.assertIn("WINDOWS_USER_PATH", rules)
            self.assertIn("NON_EXAMPLE_EMAIL", rules)
            self.assertIn("ID_MOBILE_PHONE", rules)
            self.assertIn("OPENAI_KEY", rules)
            self.assertIn("BLOCKLIST_TERM", rules)
            self.assertIn("FORBIDDEN_LOCAL_FILE", rules)


if __name__ == "__main__":
    unittest.main()
