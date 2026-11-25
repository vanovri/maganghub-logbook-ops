# MagangHub Monev Form Procedure (Gate-Verified Auto-Submit + `--draft-only` Fallback)

> [!IMPORTANT]
> **Fail-Closed Submission Guardrails**
> - Default `prepare-fill` emits `submit_mode: "auto_submit"` (allowing the agent to tick the confirmation checkbox and click **Simpan dan Kirim** once). Pass `--draft-only` to pause before the checkbox for manual review.
> - **Never** tick or submit if Delivery Gate (`G-1`..`G-8`) or safety checks (`S-1`..`S-3`) failed, if the date is already submitted (`SUBMITTED_BY_HUMAN` / `AUTO_SUBMITTED`), or if readback of any of the 3 `textarea.value` strings does not match byte-for-byte.
> - **Never** bypass login/SSO gates, Cloudflare, CAPTCHA challenges, or placement geofence/date locks, and do not require external browser relay extensions.

## Portal URLs & Field Mapping

- **Auth Preflight**: `https://monev.maganghub.kemnaker.go.id/dashboard/evaluasi`
  - Logged-in state displays tabs: `Beranda`, `Riwayat`, `Perkembangan`, `Akun`.
- **Today Form**: `https://monev.maganghub.kemnaker.go.id/dashboard` -> click **Isi Laporan Hari Ini**.
- **Edit Specific Date**: `https://monev.maganghub.kemnaker.go.id/dashboard/riwayat?date=YYYY-MM-DD&view=edit`
- **Confirmation Checkbox**: `Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar`
- **Submit Button**: `Simpan dan Kirim`

| Portal Field | JSON Key | Verbatim Textarea Placeholder | Shape |
|---|---|---|---|
| `Uraian aktivitas` | `aktivitas` | `Tulis uraian aktivitas minimal 100 karakter` | 3-5 `- ` bullets (`>= 100` chars) |
| `Pembelajaran yang diperoleh` | `pelajaran` | `Tulis ilmu/pembelajaran yang diperoleh minimal 100 karakter` | 1 paragraph (`>= 100` chars) |
| `Kendala yang dialami` | `kendala` | `Tulis kendala/hambatan yang dialami minimal 100 karakter` | 1 paragraph (`>= 100` chars) |

## Safe Fill & Auto-Submit Procedure

1. Run `python <skill-dir>/scripts/logbook_ops.py prepare-fill --date YYYY-MM-DD` (add `--draft-only` to stop before ticking/submitting, or `--strict-warnings` to fail closed on any warning). Confirm `ok: true` and verify the date is not already submitted.
2. Using your agent's built-in browser tool, check existing tabs first or open the preflight URL once.
   - If redirected to login/SSO or gated by any anti-bot/CAPTCHA screen: **stop immediately** (no polling, no bypass), and display the paste-ready draft file (`<data-dir>/drafts/YYYY-MM-DD_report.txt`) for manual copy-paste.
3. Verify the target date is `Belum Diisi` or `Perlu Tindakan Anda`. Never overwrite an already-submitted report.
4. Open the edit route **once** (do not re-call `open()` on an already-open Monev tab, as reloading the SPA clears typed text).
5. Wait for `textarea` to render (`"Memuat halaman"` disappears in ~1-4s), type into each `textarea[placeholder="..."]` using framework-triggering input events (so the live `0 / 5000` counter updates), and **read back all 3 `textarea.value` strings** to confirm exact parity.
6. Branch on `submit_guards`:
   - If `draft_only` (`tick_confirmation_checkbox: false`): leave the checkbox unchecked, report the verified draft to the user, and wait for the user to review, tick, submit, and run `confirm --mode human`.
   - If `auto_submit` (`tick_confirmation_checkbox: true` and `click_simpan_dan_kirim: true`): tick `Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar` and click **Simpan dan Kirim** **once**.
7. Verify portal response before recording completion:
   - MagangHub enforces server-side submission for **today's date at the placement location** (geofence). If the portal rejects submission (e.g., date/location error or reference code), **stop immediately**, report the exact portal message/code to the user, and **do NOT** run `confirm`.
   - Only after the portal confirms the report is saved/submitted, run `confirm --date YYYY-MM-DD --actual-minutes <MINUTES> --revisions 0 --mode auto`.
