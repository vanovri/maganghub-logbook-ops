#!/usr/bin/env python3
"""Pre-publish leak scanner for credentials, PII, local OS paths, and custom blocklists.

Pure Python 3.9+ stdlib only. Zero private names or PII are embedded in this script;
supply organization/client/personal blocklist terms via --blocklist or --blocklist-file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", "drafts"}
FORBIDDEN_EXTENSIONS = {".csv", ".env"}
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}

# Note: build patterns cleanly so static scanners never confuse regex source with real secrets.
LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SECRET_ASSIGNMENT", re.compile(r"\b(?:password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token|otp)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{4,}", re.IGNORECASE)),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("PRIVATE_KEY_HEADER", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("WINDOWS_USER_PATH", re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'`]+", re.IGNORECASE)),
    ("WSL_UNC_PATH", re.compile(r"\\\\wsl(?:\.localhost|\$)\\[^\s\"'`]+", re.IGNORECASE)),
    ("MACOS_USER_PATH", re.compile(r"(?<![A-Za-z0-9_])/Users/[A-Za-z0-9._-]+(?:/|(?=\s|$|[\"'`]))")),
    ("LINUX_HOME_PATH", re.compile(r"(?<![A-Za-z0-9_])/home/[A-Za-z0-9._-]+(?:/|(?=\s|$|[\"'`]))")),
    ("ID_MOBILE_PHONE", re.compile(r"(?<!\d)(?:\+62\s?8\d{1}[-\s]?\d{3,4}[-\s]?\d{3,5}|08[1-9]\d{1}[-\s]?\d{3,4}[-\s]?\d{3,5})(?!\d)")),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def _compile_block_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    prefix = r"(?<!\w)" if term and term[0].isalnum() else ""
    suffix = r"(?!\w)" if term and term[-1].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096]


def scan_directory(
    root: Path,
    *,
    blocklist: list[str] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    scanned_files = 0

    compiled_block: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for term in blocklist or []:
        t = term.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            compiled_block.append((t, _compile_block_pattern(t)))

    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if not path.is_file():
            continue

        rel_str = path.relative_to(root).as_posix()
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS or path.name.startswith(".env."):
            findings.append({"file": rel_str, "line": 0, "rule": "FORBIDDEN_LOCAL_FILE", "match": path.name})

        try:
            raw = path.read_bytes()
        except OSError as exc:
            findings.append({"file": rel_str, "line": 0, "rule": "UNREADABLE_FILE", "match": str(exc)})
            continue

        if _is_binary(raw):
            continue
        scanned_files += 1
        text = raw.decode("utf-8", errors="replace")

        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pat in LEAK_PATTERNS:
                m = pat.search(line)
                if m:
                    findings.append({"file": rel_str, "line": lineno, "rule": rule, "match": m.group(0)[:80]})

            for em in EMAIL_RE.finditer(line):
                domain = em.group(1).lower()
                if domain not in SAFE_EMAIL_DOMAINS:
                    findings.append({"file": rel_str, "line": lineno, "rule": "NON_EXAMPLE_EMAIL", "match": em.group(0)})

            for term, bpat in compiled_block:
                bm = bpat.search(line)
                if bm:
                    findings.append({"file": rel_str, "line": lineno, "rule": "BLOCKLIST_TERM", "match": term})

    return {
        "ok": len(findings) == 0,
        "root": str(root),
        "scanned_files": scanned_files,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_blocklist(csv_terms: str, file_path: str) -> list[str]:
    terms = [t.strip() for t in csv_terms.split(",") if t.strip()]
    if file_path:
        with Path(file_path).open("r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#"):
                    terms.append(cleaned)
    return terms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repository for secrets, PII, local OS paths, and blocklist terms.")
    parser.add_argument("target", nargs="?", default=".", help="Directory to scan (default: .)")
    parser.add_argument("--blocklist", default="", help="Comma-separated private/confidential terms to reject")
    parser.add_argument("--blocklist-file", default="", help="Optional file of blocklist terms (one per line)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    terms = _load_blocklist(args.blocklist, args.blocklist_file)
    report = scan_directory(Path(args.target), blocklist=terms)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if report["ok"]:
            print(f"CLEAN: scanned {report['scanned_files']} files, 0 leak findings.")
        else:
            for item in report["findings"]:
                print(f"LEAK [{item['rule']}] {item['file']}:{item['line']} -> {item['match']}")
            print(f"FAILED: {report['finding_count']} finding(s) across {report['scanned_files']} files.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
