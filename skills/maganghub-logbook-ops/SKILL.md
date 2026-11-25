---
name: maganghub-logbook-ops
description: "Draft, validate, track, pre-fill, and gate-verified auto-submit daily reports on the MagangHub Monev portal (Kemnaker) from today's agent chats, git commits, and user notes. Enforces 14 Indonesian writing rules, secret/NDA checks, and --draft-only manual review opt-out."
license: MIT
compatibility: Python 3.9+ (standard library only). Browser pre-fill and gate-verified auto-submit use the agent's built-in browser tool; without login or browser access, outputs copy-paste text.
allowed-tools: Read Bash Glob Grep
---

# maganghub-logbook-ops

Drafts the daily MagangHub Monev report from real work evidence, enforces the Delivery Gate and privacy guardrails, records compliance/time-saving metrics, and performs gate-verified auto-submit (with `--draft-only` opt-out) using your agent's built-in browser tool.

> [!IMPORTANT]
> **Hard Invariants**
> 1. **Indonesian output only**: all three report fields (`Uraian aktivitas`, `Pembelajaran yang diperoleh`, `Kendala yang dialami`) are always written in standard Indonesian with no first-person pronouns.
> 2. **Gate-verified auto-submit (with `--draft-only` opt-out)**: only tick the confirmation checkbox and click **Simpan dan Kirim** after Delivery Gate (`G-1`..`G-8`) and safety checks (`S-1`..`S-3`) pass, portal status is `Belum Diisi`/`Perlu Tindakan Anda`, and exact 3-field `textarea.value` parity is verified; pass `--draft-only` to stop before submitting.
> 3. **No bypasses or relay bloat**: never bypass login/SSO/CAPTCHA/anti-bot/geofence checks and do not require external browser relay extensions.

Invocation: `/maganghub-logbook-ops [user notes]` (`<skill-dir>` is this skill's installed directory).

## Workflow

| Step | Action | Tool / Reference |
|---|---|---|
| 1 | Collect evidence (`chats` + `git` + `--notes`, auto-redacted) | `<skill-dir>/scripts/collect_today.py` or `<skill-dir>/scripts/logbook_ops.py collect` |
| 2 | Filter routine noise, verify struggles & numbers (`W-01`..`W-03`) | Ask user if evidence is missing or struggle is unknown |
| 3 | Draft 3 Indonesian fields | `references/writing-rules.md`, `references/examples.md` |
| 4 | Run Delivery Gate (`G-1`..`G-8`) & safety checks (`S-1`..`S-3`) | `<skill-dir>/scripts/check_report.py` |
| 5 | Record CSV ledger & paste-ready draft file | `<skill-dir>/scripts/logbook_ops.py record` |
| 6 | Prepare, pre-fill & verify 3-field parity, then tick & click **Simpan dan Kirim** (or pass `--draft-only` to pause; copy-paste fallback if blocked) | `<skill-dir>/scripts/logbook_ops.py prepare-fill`, `references/form.md` |
| 7 | Confirm submission status (`AUTO_SUBMITTED` or `SUBMITTED_BY_HUMAN`) only after portal success is verified | `<skill-dir>/scripts/logbook_ops.py confirm` |

## Quick Commands

```bash
python <skill-dir>/scripts/logbook_ops.py collect --date 2026-11-24 --notes "Review modul autentikasi"
python <skill-dir>/scripts/logbook_ops.py gate --json-file report.json --sensitive-terms "ClientA"
python <skill-dir>/scripts/logbook_ops.py record --date 2026-11-24 --json-input report.json --sensitive-terms "ClientA"
python <skill-dir>/scripts/logbook_ops.py prepare-fill --date 2026-11-24
# Optional manual-review pause before checkbox/submit:
python <skill-dir>/scripts/logbook_ops.py prepare-fill --date 2026-11-24 --draft-only
python <skill-dir>/scripts/logbook_ops.py confirm --date 2026-11-24 --actual-minutes 3.0 --revisions 0 --mode auto
```
