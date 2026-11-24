# MagangHub Monev Form Procedure (Portable Built-in Browser + Copy-Paste Fallback)

> [!IMPORTANT]
> **Human-in-the-Loop Guarantee**
> Never tick the confirmation checkbox (`Saya menyatakan telah meninjau dan memastikan isian laporan ini sudah benar`) and never click **Simpan dan Kirim**. Submitting also records daily attendance.
> Never attempt to bypass login gates, SSO, Cloudflare, or CAPTCHA challenges, and do not require external browser relay extensions.

## Portal URLs & Field Mapping

- **Auth Preflight**: `https://monev.maganghub.kemnaker.go.id/dashboard/evaluasi`
  - Logged-in state displays tabs: `Beranda`, `Riwayat`, `Perkembangan`, `Akun`.
- **Today Form**: `https://monev.maganghub.kemnaker.go.id/dashboard` -> click **Isi Laporan Hari Ini**.
- **Edit Specific Date**: `https://monev.maganghub.kemnaker.go.id/dashboard/riwayat?date=YYYY-MM-DD&view=edit`

| Portal Field | JSON Key | Verbatim Textarea Placeholder | Shape |
|---|---|---|---|
| `Uraian aktivitas` | `aktivitas` | `Tulis uraian aktivitas minimal 100 karakter` | 3-5 `- ` bullets (`>= 100` chars) |
| `Pembelajaran yang diperoleh` | `pelajaran` | `Tulis ilmu/pembelajaran yang diperoleh minimal 100 karakter` | 1 paragraph (`>= 100` chars) |
| `Kendala yang dialami` | `kendala` | `Tulis kendala/hambatan yang dialami minimal 100 karakter` | 1 paragraph (`>= 100` chars) |

## Safe Fill Procedure

1. Run `python scripts/logbook_ops.py prepare-fill --date YYYY-MM-DD` to generate and verify the exact field payload and check that the date is not already `SUBMITTED_BY_HUMAN`.
2. Using your agent's built-in browser tool, check existing tabs first or open the preflight URL once.
   - If redirected to login/SSO or gated by any anti-bot/CAPTCHA screen: **stop immediately** (no polling, no bypass), and display the paste-ready draft file (`<data-dir>/drafts/YYYY-MM-DD_report.txt`) for manual copy-paste.
3. Verify the target date is `Belum Diisi` or `Perlu Tindakan Anda`. Never overwrite an already-submitted report.
4. Open the edit route **once** (do not re-call `open()` on an already-open Monev tab, as reloading the SPA clears typed text).
5. Wait for `textarea` to render (`"Memuat halaman"` disappears in ~1-4s), type into each `textarea[placeholder="..."]` using framework-triggering input events (so the live `0 / 5000` counter updates), and read back all 3 `textarea.value` strings to confirm exact parity.
6. **Stop before submit**: confirm the checkbox is unchecked, report the verified draft to the user, and wait for the user to review, tick, submit, and run `confirm`.
