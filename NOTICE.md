# Attribution & Upstream Notice

This project incorporates and extends ideas, writing rules, Delivery Gate checks, and MagangHub Monev portal field mappings from:

- **Upstream project**: [`raditsoic/maganghub-autofill`](https://github.com/raditsoic/maganghub-autofill)
- **License**: MIT License (`Copyright (c) 2026 raditsoic`)
- **Audited baseline commit**: `e14d86a5960103c23a138642120ddf50888f3204` (`2026-11-06`)

## Inherited from `raditsoic/maganghub-autofill` (MIT)
- The 14 Indonesian daily-report writing rules (`W-01`..`W-50`, impersonal active-verb bullet structure, no fabricated struggles, no clichés, no em dash).
- The automated Delivery Gate checks (`G-1`..`G-8`) implemented in `scripts/check_report.py`.
- The verified MagangHub Monev form flow, verbatim textarea placeholders, and strict human-in-the-loop stop before ticking the confirmation checkbox or clicking **Simpan dan Kirim**.
- The local chat prompt + git commit collector pattern (`scripts/collect_today.py`).

## New Additions & Security Hardening
- Cross-platform UTF-8 file I/O, strict `YYYY-MM-DD` ISO validation, subprocess timeouts, and automatic secret redaction in `scripts/collect_today.py`.
- Safety guardrails in `scripts/check_report.py` & `scripts/logbook_ops.py`: credential leak detection, optional customizable `--sensitive-terms` NDA blocking, optional occupational-safety/authority boundary rules, raw-notes numeric consistency warnings, 3-day Jaccard duplicate-drift detection, overwrite guard, CSV compliance ledger, and 2-week median speed tracking (`<= 4` min/day target).
- `scripts/leak_check.py`: pre-publish PII, local filesystem path, credential, and custom blocklist scanner.
- Portable browser / copy-paste fallback workflow in `skills/maganghub-logbook-ops/references/form.md` with zero unpacked browser extension dependency.
