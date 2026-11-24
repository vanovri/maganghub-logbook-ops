# Report Examples

Adapted from `raditsoic/maganghub-autofill` (MIT). Use for tone and structure only; facts always come from that day's real evidence.

## 1. Normal Workday with Real Blocker

**Uraian aktivitas**
```text
- Membuat endpoint login berbasis JWT pada layanan backend beserta skema validasi inputnya.
- Menulis tes unit untuk memverifikasi penanganan token valid dan token kedaluwarsa.
- Memperbaiki urutan middleware autentikasi yang sebelumnya menolak header token yang sah.
```

**Pembelajaran yang diperoleh**
```text
Pemahaman tentang alur verifikasi token akses dan pengujian kasus token kedaluwarsa secara terpisah bertambah. Urutan pendaftaran middleware pada permintaan HTTP terbukti menentukan keberhasilan pembacaan header autentikasi.
```

**Kendala yang dialami**
```text
Token yang sah sempat ditolak oleh layanan karena middleware autentikasi berjalan sebelum middleware pembaca header permintaan. Masalah ditelusuri melalui log permintaan dan diselesaikan dengan menukar urutan kedua middleware tersebut.
```

## 2. Workday Without Notable Technical Struggles (User Confirmed)

**Uraian aktivitas**
```text
- Memperbarui dokumentasi instalasi proyek beserta contoh konfigurasi variabel lingkungan lokal.
- Menyusun daftar prasyarat dependensi standar agar langkah penyiapan mudah direproduksi.
- Menguji seluruh langkah instalasi dari awal pada direktori bersih untuk memastikan akurasi panduan.
```

**Pembelajaran yang diperoleh**
```text
Dokumentasi instalasi perlu diuji langsung pada lingkungan bersih agar langkah yang terlewat segera terlihat. Pemisahan antara variabel wajib dan opsional mempermudah penyiapan layanan oleh anggota tim baru.
```

**Kendala yang dialami**
```text
Tidak ada kendala teknis berarti pada kegiatan hari ini. Seluruh langkah penyiapan berjalan sesuai dokumentasi saat diuji ulang pada lingkungan bersih tanpa memerlukan perbaikan tambahan.
```

## 3. Bad Example (Rejected by Delivery Gate)

```text
Hari ini saya sangat senang bisa belajar hal luar biasa — semua bug teratasi 100%, semoga bermanfaat!
```

Violations: `W-10` (`saya`), `W-21` (`luar biasa`), `W-22` (`—`), `W-23` (hyperbole), `W-50` (`semoga`), `G-5` (not 3-5 active bullets), `G-1` (< 100 chars).
