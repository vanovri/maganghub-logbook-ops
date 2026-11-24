---
name: maganghub-logbook-ops
description: "Draft, validate, track, and safely pre-fill daily reports on the MagangHub Monev portal (Kemnaker) from today's agent chats, git commits, and user notes. Enforces 14 Indonesian writing rules, secret/NDA checks, and strict human-in-the-loop stop before ticking the confirmation checkbox or submitting."
license: MIT
compatibility: Python 3.9+ (standard library only). Optional browser pre-fill uses the agent's built-in browser tool; without login or browser access, outputs copy-paste text.
allowed-tools: Read Bash Glob Grep
---

# maganghub-logbook-ops

Drafts the daily MagangHub Monev report from real work evidence, enforces the Delivery Gate and privacy guardrails, records compliance/time-saving metrics, and optionally pre-fills the form using your agent's built-in browser tool.

> [!IMPORTANT]
> **Hard Invariants**
> 1. **Indonesian output only**: all three report fields (`Uraian aktivitas`, `Pembelajaran yang diperoleh`, `Kendala yang dialami`) are always written in standard Indonesian with no first-person pronouns.
> 2. **Human submits only**: never tick the confirmation checkbox and never click **Simpan dan Kirim**.
> 3. **No bypasses or relay bloat**: never bypass login/SSO/CAPTCHA/anti-bot checks and do not require external browser relay extensions.

## Workflow

| Step | Action | Tool / Reference |
|---|---|---|
| 1 | Collect evidence (`chats` + `git` + `--notes`, auto-redacted) | `scripts/collect_today.py` or `scripts/logbook_ops.py collect` |
| 2 | Filter routine noise, verify struggles & numbers (`W-01`..`W-03`) | Ask user if evidence is missing or struggle is unknown |
| 3 | Draft 3 Indonesian fields | `references/writing-rules.md`, `references/examples.md` |
| 4 | Run Delivery Gate (`G-1`..`G-8`) & safety checks (`S-1`..`S-3`) | `scripts/check_report.py` |
| 5 | Record CSV ledger & paste-ready draft file | `scripts/logbook_ops.py record` |
| 6 | Prepare & pre-fill in built-in browser (or copy-paste fallback) | `scripts/logbook_ops.py prepare-fill`, `references/form.md` |
| 7 | User reviews, ticks confirmation checkbox, clicks **Simpan dan Kirim**, confirms | `scripts/logbook_ops.py confirm` |

## Quick Commands

```bash
python scripts/logbook_ops.py collect --date 2026-11-24 --notes "Review modul autentikasi"
python scripts/logbook_ops.py gate --json-file report.json --sensitive-terms "ClientA"
python scripts/logbook_ops.py record --date 2026-11-24 --json-input report.json --sensitive-terms "ClientA"
python scripts/logbook_ops.py prepare-fill --date 2026-11-24
python scripts/logbook_ops.py confirm --date 2026-11-24 --actual-minutes 3.0 --revisions 0
```
