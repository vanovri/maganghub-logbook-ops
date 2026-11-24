"""Public repository hygiene & licensing guardrails."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import leak_check as scanner


class TestPublicHygiene(unittest.TestCase):
    def test_repository_has_no_leaks_or_csv_files(self) -> None:
        report = scanner.scan_directory(REPO_ROOT)
        self.assertTrue(report["ok"], f"Leak findings: {json.dumps(report['findings'], indent=2)}")
        csv_files = list(REPO_ROOT.rglob("*.csv"))
        self.assertEqual(csv_files, [], f"Forbidden CSV files found: {csv_files}")

    def test_mit_license_and_upstream_attribution_present(self) -> None:
        license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        notice_text = (REPO_ROOT / "NOTICE.md").read_text(encoding="utf-8")
        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("MIT License", license_text)
        self.assertIn("raditsoic", license_text)
        self.assertIn("raditsoic/maganghub-autofill", notice_text)
        self.assertIn("raditsoic/maganghub-autofill", readme_text)

    def test_no_browser_relay_extension_bloat_in_docs(self) -> None:
        combined = "\n".join(
            p.read_text(encoding="utf-8")
            for p in REPO_ROOT.rglob("*.md")
        ).lower()
        self.assertNotIn("browser-relay install", combined)
        self.assertNotIn("load unpacked", combined)

    def test_self_contained_skill_layout(self) -> None:
        skill_root = REPO_ROOT / "skills" / "maganghub-logbook-ops"
        expected_files = [
            skill_root / "SKILL.md",
            skill_root / "scripts" / "collect_today.py",
            skill_root / "scripts" / "check_report.py",
            skill_root / "scripts" / "logbook_ops.py",
            skill_root / "references" / "writing-rules.md",
            skill_root / "references" / "form.md",
            skill_root / "references" / "examples.md",
        ]
        for path in expected_files:
            self.assertTrue(path.is_file(), f"Missing skill file: {path}")

        root_py = sorted(p.name for p in (REPO_ROOT / "scripts").glob("*.py"))
        self.assertEqual(root_py, ["leak_check.py"])

    def test_installers_and_plugin_manifests(self) -> None:
        install_sh = REPO_ROOT / "install.sh"
        install_ps1 = REPO_ROOT / "install.ps1"
        self.assertTrue(install_sh.is_file(), "Missing install.sh")
        self.assertTrue(install_ps1.is_file(), "Missing install.ps1")
        self.assertNotIn(b"\r", install_sh.read_bytes(), "install.sh must use LF line endings only")

        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["name"], "maganghub-logbook-ops")
        self.assertEqual(marketplace["plugins"][0]["name"], "maganghub-logbook-ops")
        self.assertEqual(plugin["name"], "maganghub-logbook-ops")
        self.assertIn("./skills/", plugin["skills"])


if __name__ == "__main__":
    unittest.main()
