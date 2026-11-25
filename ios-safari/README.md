# Panduan iOS Safari & iOS Shortcuts (`maganghub-logbook-ops`)

Toolkit pendamping tanpa dependensi (*Python 3.9+ standard library only*) untuk mengubah rekapan logbook Excel (`.xlsx`) atau `.csv` menjadi JSON yang sudah lolos validasi 14 aturan `Delivery Gate`, lalu mengisinya langsung dari **Safari iPhone/iPad** dalam hitungan detik.

> [!IMPORTANT]
> **Aturan Keamanan & Batas Portal**
> - **Wajib hari-H & lokasi kantor (`geofence`)**: server `monev.maganghub.kemnaker.go.id` hanya menerima pengiriman untuk tanggal hari ini di lokasi penempatan.
> - **Tanpa bypass**: login SSO, izin lokasi GPS Safari, dan verifikasi anti-bot tetap dijalankan secara normal di Safari asli.
> - **Jaga kualitas isi**: logbook yang dikirim langsung masuk status *Menunggu Persetujuan* mentor. Gunakan Excel sebagai kerangka draf, lalu sesuaikan seperlunya jika ada pekerjaan harian yang berbeda agar terhindar dari revisi.

---

## 1. Siapkan File Excel / CSV

Siapkan 4 kolom pada sheet pertama (nama kolom fleksibel, huruf besar/kecil bebas):

| `tanggal` | `aktivitas` | `pelajaran` | `kendala` |
|---|---|---|---|
| `2026-11-25` atau `25 Nov 2026` | 3–5 baris diawali `- ` dengan kata kerja aktif `meN-` (min 100 karakter) | 1 paragraf ringkas tanpa enter/bullet (min 100 karakter) | 1 paragraf kendala nyata tanpa mengarang (min 100 karakter) |

Untuk membuat contoh CSV cepat (simpan di luar folder repo agar tidak ikut ter-commit):

```bash
python ios-safari/excel_to_ios_json.py --write-sample-csv ../sample_logbooks.csv
```

---

## 2. Konversi & Validasi di PC (`excel_to_ios_json.py`)

Jalankan dari root repo (tidak perlu `pip install`, langsung jalan dengan Python bawaan):

```bash
# Hasilkan logbooks.json + skrip siap pakai untuk iOS Shortcuts & Userscripts
python ios-safari/excel_to_ios_json.py ./logbook_6_bulan.xlsx \
  --sensitive-terms "NamaKlienRahasia,ProyekX" \
  --out ./logbooks.json \
  --emit-shortcut-js ./my_ios_shortcut.js \
  --emit-userscript ./my_maganghub.user.js
```

Opsi berguna:
- `--sheet "NamaSheet"`: pilih sheet tertentu di `.xlsx`.
- `--date-col` / `--aktivitas-col` / `--pelajaran-col` / `--kendala-col`: isi nama header atau nomor kolom (`1`, `2`, dst.) jika struktur kolom berbeda.
- `--draft-only`: matikan auto-submit pada file JS yang dihasilkan (berhenti sebelum centang konfirmasi & klik **Simpan dan Kirim**).
- `--skip-invalid`: lewati baris yang gagal validasi dan tetap ekspor baris yang lolos.
- `--no-gate`: lewati cek gaya penulisan `G-1`..`G-8` (cek rahasia/kredensial `S-1` dan keamanan `S-2`/`S-3` tetap aktif).

---

## 3A. Cara Pakai via Apple iOS Shortcuts (Gratis, Tanpa Aplikasi Tambahan)

1. **Aktifkan izin skrip (sekali saja):** di iPhone buka **Settings → Shortcuts → Advanced → aktifkan Allow Running Scripts**.
2. **Buat Shortcut baru** di aplikasi **Shortcuts**:
   - Centang **Show in Share Sheet** (hanya tipe *Safari web pages*).
   - Tambahkan aksi **Run JavaScript on Web Page**.
   - Buka file `./my_ios_shortcut.js` hasil langkah 2 (kirim via AirDrop / iCloud Drive), salin seluruh isinya, lalu tempel ke kolom kode **Run JavaScript on Web Page**.
3. **Pemakaian harian (~5 detik di kantor):**
   - Buka `https://monev.maganghub.kemnaker.go.id/dashboard` di **Safari iOS**, pastikan sudah login dan klik **Isi Laporan Hari Ini**.
   - Ketuk tombol **Share** (ikon kotak + panah ke atas) → pilih Shortcut **Isi Logbook**.
   - Skrip otomatis mencocokkan tanggal lokal/URL, mengisi 3 kotak form, memverifikasi *parity* teks, mencentang pernyataan, dan mengklik **Simpan dan Kirim** satu kali.

---

## 3B. Cara Pakai via Ekstensi Userscripts di Safari iOS (Impor File JSON Langsung)

Cocok kalau jadwal Excel sering diperbarui tanpa mau edit ulang Shortcut:

1. Pasang aplikasi **Userscripts** (gratis di App Store) dan aktifkan di **Settings → Safari → Extensions → Userscripts** (beri izin untuk `monev.maganghub.kemnaker.go.id`).
2. Simpan `ios-safari/safari_userscript.user.js` (atau `./my_maganghub.user.js`) ke folder Userscripts di iCloud/Files, lalu simpan `logbooks.json` di aplikasi **Files** iPhone.
3. Buka halaman form edit Monev di Safari iOS:
   - Panel kecil **Logbook Ops** muncul di pojok kanan bawah.
   - Ketuk **Import JSON** sekali untuk memuat `logbooks.json` ke penyimpanan lokal Safari (*localStorage*).
   - Pastikan sakelar **Auto-submit** sesuai keinginan (bawaan aktif; matikan kapan saja untuk mode *draft-only*), lalu ketuk **Isi Logbook**.
