# Panduan Handoff Implementasi — POS Jou Coffee

Dokumen ini merangkum fondasi aplikasi yang sudah tersedia dan membantu programmer junior atau model AI melanjutkan pekerjaan dengan aman. Dokumen kebutuhan produk tetap berada di [PRD.md](./PRD.md); urutan menuju rilis aman ada di [RELEASE_PLAN.md](./RELEASE_PLAN.md).

## 1. Gambaran Sistem

Proyek terdiri dari tiga aplikasi:

1. **Backend Flask** (`backend/`) — API untuk login, menu, transaksi, stok, shift/kas, laporan, QR Menu, dan integrasi pembayaran.
2. **Aplikasi kasir Flutter** (`mobile/`) — UI kasir dan pengelolaan untuk Android/iOS; memakai SQLite lokal untuk katalog POS tersimpan dan transaksi POS yang belum tersinkron.
3. **QR Menu PWA** (`qr-menu/`) — aplikasi web pelanggan untuk melihat menu, mengirim pesanan, dan mengikuti status/pembayaran pesanan.

Saat server tersedia, alur utamanya:

```text
Flutter / QR Menu → Flask API → MySQL/MariaDB
                         ↑
                 koneksi lokal XAMPP

Flutter offline → SQLite perangkat → antrean POS → Flask API saat tersambung
```

MySQL/MariaDB XAMPP adalah database backend lokal di komputer pengembang. HP tidak terhubung langsung ke MySQL; HP mengakses Flask API melalui alamat IPv4 komputer. SQLite pada HP adalah database terpisah untuk data offline.

## 2. Teknologi dan Lokasi Kode

| Bagian | Teknologi | Lokasi utama |
|---|---|---|
| Backend dan API | Flask, SQLAlchemy, JWT, Marshmallow, Flask-SocketIO | `backend/app/` |
| Database backend | MySQL/MariaDB untuk development XAMPP; SQLite in-memory untuk tes | `backend/app/config.py`, `backend/.env.example` |
| Aplikasi mobile | Flutter, Riverpod, GoRouter, Dio | `mobile/lib/` |
| Database lokal mobile | SQLite melalui Drift | `mobile/lib/src/data/local/` |
| Sinkronisasi POS | Cache katalog, antrean transaksi lokal, retry/idempotency | `mobile/lib/src/data/pos_repository.dart` |
| Menu pelanggan | React, TypeScript, Vite, PWA | `qr-menu/src/` |

Folder backend dibagi menurut fungsi, seperti `auth`, `catalog`, `orders`, `inventory`, `finance`, `reports`, `tables`, `sync`, dan `public`. Route API didaftarkan melalui application factory di `backend/app/__init__.py`.

## 3. Fitur yang Sudah Dibangun

### Backend

- Login dan token JWT; otorisasi berbasis role Kasir, Admin/Owner, dan Super Admin.
- Endpoint katalog POS, pesanan, status pesanan, dan inbox pesanan QR yang menunggu approval.
- Endpoint manajemen kategori, menu, bahan, satuan, resep, stok, pembelian, dan stock opname sesuai cakupan yang sudah tersedia.
- Endpoint pengeluaran dan kategori pengeluaran, shift/kas, laporan, pengguna/perangkat, dan konfigurasi meja/QR.
- QR Menu publik untuk membaca menu, mengirim pesanan, dan melihat status.
- Integrasi teknis Midtrans QRIS di backend, termasuk alur charge/status/webhook. Penggunaan sungguhan tetap memerlukan kredensial merchant valid dan tes end-to-end.
- Health check `GET /api/v1/health` memeriksa API dan koneksi database.
- Development dapat berjalan tanpa Redis untuk satu proses; konfigurasi production mensyaratkan infrastruktur/secret yang lebih lengkap.

### Aplikasi Flutter

- Login dan penyimpanan sesi; navigasi POS, pesanan, laporan, akun, dan layar manajemen sesuai role.
- POS untuk dine-in, take-away, dan delivery/channel; data katalog yang berhasil dimuat dapat digunakan kembali saat server tidak dapat dijangkau.
- Transaksi POS yang gagal dikirim karena koneksi atau gangguan server disimpan ke SQLite, dapat dilihat pada antrean, dan bisa dicoba sinkron kembali.
- Retry transaksi memakai idempotency key agar permintaan ulang tidak membuat pesanan server ganda.
- Indikator koneksi dan jumlah transaksi tertunda.
- Komponen cetak Bluetooth ESC/POS, QR meja, serta koneksi WebSocket tersedia dalam aplikasi.
- Android mencoba sinkronisasi terjadwal; iOS terutama mencoba kembali saat aplikasi aktif. Jadwal background iOS tidak dijamin sistem operasi.

### QR Menu PWA

- Web pelanggan untuk membuka menu menggunakan token meja, membuat pesanan, melihat status, dan mengikuti alur QRIS.
- Proxy API tersedia di server development Vite.
- PWA menyimpan app shell; menu dan status pesanan tetap membutuhkan API aktif.

## 4. Batasan Penting yang Jangan Diasumsikan Sudah Selesai

- **Offline belum mencakup seluruh aplikasi.** SQLite mobile saat ini terutama mencakup cache katalog POS dan antrean transaksi POS. Login, manajemen, laporan, inbox pesanan QR, dan operasi server lain memerlukan backend yang dapat dijangkau.
- **Jalur retry POS saat ini tidak memakai `/sync/push`.** Aplikasi mengirim ulang transaksi tertunda ke `POST /api/v1/orders`, yang mendukung idempotency key. Endpoint `/sync/push` backend saat ini hanya mencatat change log dan bukan pemroses transaksi POS.
- **Akun login pertama membutuhkan koneksi ke API.** Jangan menjanjikan login offline atau masa sesi offline tujuh hari sebelum fitur dan pengujiannya benar-benar tersedia.
- **Notifikasi FCM belum siap dipakai.** WebSocket hanya memberi realtime saat aplikasi tersambung; push memerlukan konfigurasi Firebase/APNs, registrasi token, dan pengujian perangkat.
- **QRIS bukan bukti siap produksi.** Konfigurasi Midtrans sandbox/merchant dan tes charge, webhook, status, timeout, refund, serta rekonsiliasi harus diselesaikan.
- **Cakupan manajemen dan operasi mungkin belum memenuhi seluruh PRD.** Verifikasi tiap layar terhadap API dan hak akses server; gunakan checklist `RELEASE_PLAN.md` untuk menemukan gap.
- **Dukungan iOS perlu diuji di perangkat/macOS.** Build Android berhasil tidak membuktikan perilaku iOS, printer, notifikasi, atau background sync.
- XAMPP ditujukan untuk development lokal, bukan database production.

## 5. Menjalankan Secara Lokal

### Backend dengan XAMPP

1. Nyalakan MySQL di XAMPP dan buat database `jou_coffee` lewat phpMyAdmin.
2. Dari root repository, aktifkan virtual environment dan siapkan tabel/data demo:
   ```powershell
   .\venv\Scripts\Activate.ps1
   python .\backend\seed.py
   ```
3. Jalankan API:
   ```powershell
   python .\backend\run.py
   ```
4. Pada komputer, tes `http://127.0.0.1:5000/api/v1/health`.
5. Untuk HP fisik, hubungkan HP dan komputer ke Wi-Fi privat yang sama. Cari IPv4 komputer dengan `ipconfig`, lalu buka `http://<IP-KOMPUTER>:5000/api/v1/health` dari browser HP.
6. Jika HP tidak bisa membuka API, periksa apakah Windows Firewall mengizinkan Python/port 5000 untuk profil **Private**. Jangan buka port MySQL 3306 untuk akses HP.

Jalankan seeder hanya bila perlu membuat/melengkapi data awal. Periksa `backend/.env` untuk `DATABASE_URL`; jangan salin atau membagikan secret dari file tersebut.

### Flutter di HP Android fisik

Dari folder `mobile`, jalankan dengan alamat IPv4 komputer yang benar:

```powershell
flutter pub get
flutter run `
  --dart-define=API_BASE_URL=http://192.168.1.10:5000/api/v1 `
  --dart-define=QR_MENU_BASE_URL=http://192.168.1.10:5173
```

Ganti `192.168.1.10` dengan IPv4 komputer. `10.0.2.2` hanya untuk Android Emulator; `localhost` pada HP menunjuk ke HP itu sendiri. HTTP diizinkan untuk Android debug; deployment publik harus menggunakan HTTPS.

### QR Menu di jaringan lokal

Dari folder `qr-menu`:

```powershell
npm.cmd install
npm.cmd run dev -- --host 0.0.0.0
```

Buka URL Vite menggunakan IPv4 komputer dari HP pelanggan. Proxy Vite meneruskan request `/api/v1` ke backend lokal. Jika firewall memblokir, izinkan port Vite (default 5173) untuk jaringan Private.

## 6. Validasi yang Relevan

Jalankan tes setelah menyentuh bagian terkait:

```powershell
# Backend — dari root repository
Set-Location .\backend
..\venv\Scripts\python.exe -m pytest .\tests -q

# Flutter — dari root repository
Set-Location ..\mobile
flutter analyze
flutter test

# QR Menu — dari root repository
Set-Location ..\qr-menu
npm.cmd run build
npm.cmd run lint
```

Tes backend memakai SQLite in-memory, bukan XAMPP. Karena itu tes lulus tidak menggantikan pemeriksaan koneksi ke MySQL/MariaDB XAMPP. Jalankan `git diff --check` sebelum menyelesaikan perubahan.

## 7. Cara Melanjutkan Pekerjaan

1. Baca kebutuhan yang relevan di `PRD.md`, lalu cek status dan gerbang rilis di `RELEASE_PLAN.md`.
2. Telusuri route/API backend dan pemanggilnya di Flutter/PWA sebelum mengubah kontrak data. Jangan menganggap endpoint di dokumentasi pasti sama dengan implementasi; verifikasi langsung di kode dan tes.
3. Pertahankan hak akses di backend, bukan hanya menyembunyikan tombol di UI.
4. Untuk perubahan sinkronisasi, uji mode offline, pemulihan setelah aplikasi ditutup, retry, kegagalan API, dan pengiriman ulang idempotent.
5. Tambahkan atau perbarui tes pada modul yang diubah; jalankan analyzer/build yang sesuai.
6. Jangan mencatat secret, password, token, atau data sensitif ke source control/log.
7. Jangan menandai fitur sebagai siap produksi sebelum melewati kriteria pada `RELEASE_PLAN.md`.

## 8. Referensi Kode

- Backend setup, konfigurasi XAMPP, API, dan uji: `backend/README.md`, `backend/app/`, `backend/tests/`.
- Flutter, API client, database lokal, dan retry POS: `mobile/README.md`, `mobile/lib/src/data/`, `mobile/lib/src/features/`.
- QR Menu pelanggan: `qr-menu/README.md`, `qr-menu/src/`.
- Kebutuhan produk dan urutan rilis: `PRD.md`, `RELEASE_PLAN.md`.
