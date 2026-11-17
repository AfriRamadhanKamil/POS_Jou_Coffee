# 📱 Rencana Implementasi Frontend Flutter – POS Jou Coffee (PRD v2.0)

> **Target Dokumen:** Programmer Junior / Model AI untuk implementasi mandiri per fase.
> **Karakter:** High-Level — menjelaskan *apa* yang dibangun, *batasan UX/bisnis*, dan *tolok ukur selesai*. Detail teknis (nama widget, nama variabel, dsb.) diputuskan oleh implementer selama tidak melanggar aturan di sini.
> **Fokus utama:** Aplikasi kasir Android (HP dan tablet) menggunakan Flutter yang bekerja **offline-first**, terhubung ke backend Flask, dan mendukung semua alur bisnis Jou Coffee.

---

## 1. Stack & Dependensi Flutter

| Komponen | Teknologi |
| :--- | :--- |
| Framework | Flutter (Android: HP portrait + tablet landscape) |
| State Management | Riverpod |
| Routing | go_router |
| Database Lokal (Offline) | Drift (SQLite) |
| HTTP Client | Dio |
| Deteksi Jaringan | connectivity_plus |
| Sync Latar Belakang | WorkManager (android) |
| Notifikasi Push | firebase_messaging (FCM) |
| WebSocket | web_socket_channel |
| Printer Thermal | Paket ESC/POS via Bluetooth |
| Storage Aman | flutter_secure_storage |
| Navigasi & UI | Material 3, font bahasa Indonesia |

> **Catatan:** Semua nilai uang ditampilkan dalam format Rupiah. Waktu ditampilkan dalam WIB meskipun disimpan UTC. Tombol besar dan konfirmasi untuk aksi kritis.

---

## 2. Aturan Mutlak Frontend (Wajib Dipatuhi di Semua Fase)

1. **Offline-first.** Semua aksi kasir ditulis ke SQLite lokal lebih dahulu. Layar **tidak pernah** menunggu server. Sinkronisasi berjalan di latar belakang.
2. **UUID dibuat di perangkat.** Setiap data baru mendapat UUID v4 yang dibuat di perangkat. Nomor struk berformat `JOU-{DEVICE}-{YYYYMMDD}-{SEQ}`.
3. **Role dikontrol server.** Navigasi dan menu disesuaikan role dari klaim JWT. Saat offline, role dibaca dari cache lokal yang aman. Menyembunyikan menu di UI saja tidak cukup — permintaan tetap dikirim dengan token JWT yang benar.
4. **Kasir tidak boleh melihat HPP dan laba.** Komponen laporan laba dan HPP harus sepenuhnya tidak muncul di UI Kasir, bukan hanya disembunyikan.
5. **Aksi sensitif butuh PIN Admin.** Void, refund, diskon di atas batas, dan konfirmasi QRIS statis harus memunculkan dialog verifikasi PIN Admin sebelum diproses.
6. **Responsif HP dan tablet.** Layout POS di tablet menggunakan dua panel (katalog kiri, keranjang kanan) dalam mode landscape. Di HP, layout satu panel.
7. **Bahasa Indonesia.** Semua teks UI, pesan error, dan konfirmasi dalam bahasa Indonesia.
8. **Transaksi tidak boleh hilang.** Jika terjadi crash atau koneksi terputus, data pesanan yang sudah disimpan lokal harus tetap ada dan tersinkron saat online kembali.

---

## 3. Struktur Folder Flutter

```
mobile/
├── lib/
│   ├── main.dart
│   ├── app/                     # Inisialisasi app, theme, router
│   ├── core/
│   │   ├── database/            # Drift schema & DAO
│   │   ├── network/             # Dio client, interceptor JWT, error handler
│   │   ├── sync/                # Sync engine: outbox, push, pull, WorkManager
│   │   ├── auth/                # Penyimpanan token, helper role, session manager
│   │   └── utils/               # Format Rupiah, UUID generator, format waktu WIB
│   ├── features/
│   │   ├── auth/                # Layar login (password & PIN), splash
│   │   ├── pos/                 # Layar POS utama: katalog, keranjang, bayar, struk
│   │   ├── orders_inbox/        # Inbox QR: pesanan menunggu approval kasir
│   │   ├── shift/               # Buka/tutup shift, kas masuk/keluar
│   │   ├── expense/             # Pengeluaran: tambah, daftar, foto nota
│   │   ├── report/              # Laporan penjualan, grafik (Admin: laba)
│   │   ├── management/          # Menu, bahan baku, resep, stok, meja, QR (Admin only)
│   │   └── settings/            # Profil, perangkat terdaftar, konfigurasi server
│   └── shared/                  # Widget bersama: tombol, dialog, indikator sync
├── test/
└── pubspec.yaml
```

---

## 4. Rincian Fase Implementasi

Kerjakan fase secara **berurutan**. Jangan mulai fase berikutnya sebelum kriteria **"Selesai Bila"** pada fase aktif terpenuhi.

---

### 🏗️ Fase 0 — Fondasi & Kerangka Flutter

**Tujuan:** Menyiapkan scaffold aplikasi agar seluruh fase berikutnya dapat dibangun di atasnya tanpa bongkar ulang.

**Yang dibangun:**
- Inisialisasi proyek Flutter dengan struktur folder seperti di atas.
- Pasang semua dependensi utama (Riverpod, go_router, Drift, Dio, connectivity_plus).
- Buat `AppTheme` Material 3: warna brand Jou Coffee, font, ukuran tombol besar.
- Setup go_router: definisi semua rute utama, guard redirect berdasarkan status login.
- Setup Drift: definisi skema tabel lokal yang mencerminkan data yang perlu offline (katalog, transaksi, shift, pengeluaran). Siapkan migrasi berversi.
- Setup Dio: base URL dari konfigurasi, interceptor untuk menyisipkan JWT, interceptor error handler (401 → refresh token, 403 → tampilkan pesan).
- Buat provider Riverpod dasar: `authProvider`, `connectivityProvider`, `syncStatusProvider`.
- Splash screen: cek token lokal, arahkan ke Login atau Home.
- Build ke HP dan tablet Android nyata. Pastikan tidak ada error build.

**Selesai Bila:**
- Aplikasi berhasil dibuild dan berjalan di HP dan tablet Android (Android 7.0+).
- Splash screen mengarahkan ke halaman login.
- Skema Drift terbuat di perangkat.
- Semua dependensi terpasang tanpa konflik.

---

### 🔐 Fase 1 — Autentikasi & Navigasi Berbasis Role

**Tujuan:** Pengguna dapat login, role-nya terbaca, dan navigasi menyesuaikan hak akses.

**Yang dibangun:**
- **Layar Login:** input username + password. Mode PIN Kasir: tombol toggle ke keypad 6 digit, username `kasir` terisi otomatis. Tampilkan input alamat server (URL backend) yang bisa diubah dan disimpan lokal (flutter_secure_storage).
- **Alur login online:** kirim kredensial ke `POST /auth/login`, simpan access token + refresh token ke secure storage, simpan role dan `device_id` ke cache lokal.
- **Login offline:** jika tidak ada internet, bandingkan input dengan hash password/PIN yang tersimpan lokal. Tampilkan peringatan "Mode Offline". Sesi offline maksimal 7 hari.
- **Auto-refresh token:** interceptor Dio secara otomatis mencoba `POST /auth/refresh` jika mendapat 401. Jika refresh gagal, paksa logout dan kembali ke halaman Login.
- **Navigasi berbasis role:**
  - Kasir: POS, Inbox QR, Shift, Pengeluaran, Laporan (tanpa laba).
  - Admin/Super Admin: semua menu Kasir + Manajemen (menu, inventori, meja, pengguna, perangkat), Laporan lengkap termasuk laba.
- **Logout:** hapus token dan cache lokal, kembali ke halaman Login.
- **Layar profil:** tampilkan nama, role, device_id, dan tombol logout.

**Selesai Bila:**
- Login berhasil dengan semua role (Kasir, Admin, Super Admin).
- Kasir tidak melihat menu Manajemen; Admin melihat semua menu.
- Login offline bekerja tanpa internet setelah pernah login online.
- Sesi offline lebih dari 7 hari memaksa login ulang.
- Token expired di-refresh otomatis tanpa interaksi pengguna.

---

### 🍽️ Fase 2 — Katalog Menu (Tampilan & Sinkronisasi Awal)

**Tujuan:** Katalog menu tersedia di perangkat, termasuk saat offline.

**Yang dibangun:**
- Ambil katalog dari server (`GET /catalog`) saat pertama kali login atau saat sync. Simpan ke Drift (tabel kategori, menu, varian, modifier).
- **Layar Kelola Menu (Admin only):**
  - Daftar kategori dan menu dengan foto (dari URL atau upload).
  - Form tambah/edit menu: nama, harga, foto, kategori, status aktif.
  - Kelola varian (ukuran, es, gula) dan modifier (topping, harga tambahan).
  - Kelola channel penjualan: nama platform, harga per channel, persentase komisi.
  - Soft delete: menu yang dinonaktifkan tidak muncul di POS.
- Semua perubahan ditulis ke Drift lokal terlebih dahulu, lalu masuk ke antrean sync.
- Layar ini hanya dapat diakses oleh Admin dan Super Admin. Kasir yang mencoba akses dialihkan atau ditampilkan pesan "Tidak punya akses".

**Selesai Bila:**
- Katalog muncul di perangkat baru setelah login dan sync pertama.
- Katalog tetap dapat dibuka saat internet mati.
- Admin dapat menambah, mengedit, dan menonaktifkan menu.
- Kasir tidak dapat mengakses layar kelola menu.

---

### 🔄 Fase 3 — Mesin Sinkronisasi

**Tujuan:** Data antara perangkat dan server selalu konsisten, tanpa duplikat, tanpa data hilang.

**Yang dibangun:**
- **Sync Outbox:** setiap perubahan data di Drift juga menulis satu baris ke tabel `sync_outbox` (berisi: tipe data, payload JSON, `idempotency_key` = UUID yang sudah ada di data).
- **Worker Sync:**
  - Pemicu: aplikasi dibuka, koneksi internet kembali, setelah setiap transaksi, tombol sync manual, dan terjadwal via WorkManager (setiap N menit saat aplikasi aktif).
  - Proses Push: ambil semua baris di `sync_outbox`, kirim ke `POST /sync/push` dalam batch. Jika server menerima (`200`), hapus baris dari outbox. Jika gagal, retry dengan exponential backoff.
  - Proses Pull: panggil `GET /sync/pull?cursor={last_server_version}`. Terapkan perubahan yang diterima ke Drift. Simpan `server_version` terbaru.
- **Indikator Status Sync** di UI (pojok atas atau status bar): ikon/teks yang menampilkan `Online`, `Offline`, `Menyinkronkan...`, atau `{N} data menunggu`.
- Konflik master data: data dari server menang dan menimpa data lokal.

**Selesai Bila:**
- Data yang dikirim berulang kali tidak menciptakan duplikat di server.
- Perangkat baru yang login dapat menerima semua data terbaru dari server.
- Indikator sync menampilkan status yang akurat.
- WorkManager tetap berjalan di latar belakang meski aplikasi ditutup.

---

### 🛒 Fase 4 — Layar POS (Kasir)

**Tujuan:** Kasir dapat menyelesaikan transaksi penuh, termasuk tanpa internet.

**Yang dibangun:**
- **Layout POS:**
  - HP (portrait): katalog menu (tab kategori + scroll) di halaman pertama, keranjang di halaman kedua (atau sheet).
  - Tablet (landscape): dua panel — katalog kiri, keranjang kanan — selalu terlihat.
- **Katalog:** daftar menu per kategori, pencarian teks, item favorit, tombol item besar. Item dengan label "Habis" tidak bisa dipilih.
- **Memilih Item:** tap item → pilih varian dan modifier (jika ada) → masuk ke keranjang.
- **Keranjang:**
  - Ubah qty, hapus item, tambah catatan per item.
  - Diskon per item atau per transaksi (nominal atau persen). Jika diskon di atas batas konfigurasi, tampilkan dialog PIN Admin.
  - Pilih tipe pesanan: Dine In (pilih nomor meja) atau Take Away.
  - Tampilkan total dengan format Rupiah.
- **Pembayaran:**
  - Tunai: input nominal yang diterima, tampilkan kembalian.
  - QRIS Statis: tombol konfirmasi "Uang sudah diterima" (dengan dialog konfirmasi), dicatat di audit log.
- **Simpan Transaksi:** saat "Bayar" ditekan, tulis pesanan ke Drift lokal dengan status `APPROVED`, masukkan ke `sync_outbox`. Proses ini harus selesai < 1 detik.
- **Struk:** tampilkan pratinjau struk setelah transaksi selesai. Tombol "Cetak" via Bluetooth thermal. Tombol "Bagikan PDF" sebagai fallback.
- Tiket dapur/bar dicetak terpisah dari struk pelanggan (P1).
- Void pesanan dengan PIN Admin: buat transaksi koreksi baru (P1).

**Selesai Bila:**
- 10 transaksi berturut-turut tanpa internet tersimpan semua, masing-masing < 1 detik.
- Struk berhasil dicetak di minimal 2 merek printer Bluetooth.
- Setelah online, semua transaksi terkirim ke server tanpa duplikat.
- Diskon di atas batas tidak bisa disimpan tanpa PIN Admin yang valid.

---

### 💰 Fase 5 — Shift, Kas, dan Pengeluaran

**Tujuan:** Arus kas dan biaya operasional tercatat rapi, bisa dipakai offline.

**Yang dibangun:**
- **Layar Shift:**
  - Tombol "Buka Shift" (input modal awal kas).
  - Saat shift aktif: tampilkan ringkasan kas berjalan (penjualan tunai, kas masuk, kas keluar, pengeluaran).
  - Tombol "Tutup Shift" (input kas fisik akhir). Tampilkan ringkasan perbandingan kas teoritis vs fisik dan selisihnya.
  - Admin dapat melihat riwayat semua shift dan melakukan rekonsiliasi.
- **Kas Masuk/Keluar:** form sederhana (nominal, keterangan, arah masuk/keluar). Tidak masuk ke laporan penjualan.
- **Layar Pengeluaran:**
  - Daftar pengeluaran dengan filter tanggal.
  - Form tambah pengeluaran: kategori, nominal, catatan, foto nota (kamera atau galeri).
  - Kasir: hanya lihat dan tambah. Admin: edit dan hapus (soft delete).
- Semua data shift dan pengeluaran ditulis ke Drift lokal dan masuk ke `sync_outbox`.

**Selesai Bila:**
- Shift dapat dibuka dan ditutup saat offline. Selisih kas dihitung dengan benar.
- Pengeluaran baru dapat ditambahkan saat offline dan tersinkron ke server.
- Kasir tidak dapat mengedit atau menghapus pengeluaran yang sudah ada.

---

### 📊 Fase 6 — Pesanan Online (Delivery), Laporan & Grafik

**Tujuan:** Penjualan GoFood dkk. masuk laporan, laporan akurat untuk semua role.

**Yang dibangun:**
- **Mode Pesanan Online di POS:**
  - Pilih tipe "Delivery" → pilih channel (GoFood, GrabFood, dsb.) → input ID pesanan eksternal → pilih item dengan harga per channel → input komisi (terisi otomatis dari konfigurasi channel).
  - Metode bayar "Platform" — tidak masuk saldo kas tunai.
  - Langsung berstatus `APPROVED` setelah disimpan.
- **Layar Laporan:**
  - Filter: rentang tanggal, tipe pesanan, channel, metode bayar, kasir.
  - Ringkasan: total penjualan, jumlah transaksi, rata-rata per transaksi.
  - Laporan per channel: penjualan kotor, komisi, pendapatan bersih.
  - **Kasir:** tidak melihat kolom HPP dan laba. Angka laba tidak pernah muncul di laporan Kasir.
  - **Admin/Super Admin:** tambahan laporan laba kotor (pendapatan − HPP) — data HPP berasal dari resep Fase 7.
- **Grafik:**
  - Penjualan per hari dan per jam (bar/line chart).
  - Menu terlaris (bar chart horizontal).
  - Distribusi per channel dan per tipe pesanan (pie/donut chart).
- Ekspor PDF dan Excel (P1).

**Selesai Bila:**
- Pesanan Delivery dari GoFood muncul di laporan dengan komisi yang benar, tidak masuk kas tunai.
- Angka laporan cocok dengan semua transaksi uji (POS, online, per channel).
- Kasir membuka laporan dan tidak melihat HPP atau laba sama sekali.
- Admin membuka laporan dan melihat laba kotor (setelah Fase 7 selesai).

---

### 📦 Fase 7 — Manajemen Inventori (Admin Only)

**Tujuan:** Stok bahan terpotong otomatis setiap transaksi. Kasir tidak dapat akses modul ini.

**Yang dibangun:**
- **Layar Inventori (Admin only):**
  - Kelola Satuan (pcs, ml, gram, dsb.).
  - Kelola Bahan Baku: nama, satuan, stok minimum, harga beli terakhir.
  - Kelola Resep: hubungkan menu/varian ke daftar bahan dan takaran. HPP dihitung otomatis dan ditampilkan ke Admin.
- **Pergerakan Stok (semua sebagai ledger):**
  - Stok Masuk (pembelian): input nama supplier, nominal, bahan yang dibeli.
  - Penyesuaian Manual dan Waste: alasan wajib diisi.
  - Stok Opname: input stok fisik aktual → sistem mencatat selisih sebagai pergerakan koreksi.
- **Pemotongan Stok Otomatis:** setiap kali pesanan berstatus `APPROVED` (dari POS atau sync), aplikasi mencatat pergerakan stok keluar sesuai resep. Ini terjadi di lokal (Drift) dan disinkronkan ke server.
- Layar saldo stok: tampilkan semua bahan, stok saat ini, dan tanda merah jika di bawah minimum.
- Label "Habis" muncul di POS bila stok bahan tidak mencukupi 1 porsi (P1).
- Kasir membuka halaman ini → dialihkan atau ditampilkan "Tidak punya akses".

**Selesai Bila:**
- Menjual 1 menu mengurangi stok bahan sesuai resep di perangkat lokal.
- Stok opname menghasilkan pergerakan koreksi yang tersinkron ke server.
- Kasir tidak dapat mengakses modul inventori.
- HPP per menu muncul di laporan Admin setelah resep diisi.

---

### 📱 Fase 8 — Inbox QR Menu & Notifikasi Realtime

**Tujuan:** Pesanan dari pelanggan via QR meja masuk ke perangkat kasir dalam hitungan detik.

**Yang dibangun:**
- **Layar Kelola Meja (Admin only):**
  - CRUD meja (nama/nomor, kapasitas).
  - Tombol "Generate QR" per meja → tampilkan dan cetak QR code (berisi URL web QR menu dengan token bertanda tangan).
  - Tombol "Regenerate" untuk membuat token baru (token lama langsung tidak berlaku).
- **Layar Inbox QR (semua role):**
  - Daftar pesanan dengan status `PENDING_APPROVAL` dari sumber `QR`.
  - Tiap kartu pesanan: nomor meja / nama pelanggan, daftar item, total, waktu masuk.
  - Tombol **Terima** (langsung `APPROVED`), **Tolak** (dialog alasan wajib diisi), dan **Edit** (hapus item yang habis, lalu Terima).
  - Badge jumlah pesanan menunggu di ikon navigasi Inbox QR.
- **Notifikasi Realtime:**
  - WebSocket: saat aplikasi aktif, server mengirim event pesanan baru → Inbox QR langsung diperbarui + suara notifikasi.
  - FCM Push: saat aplikasi di background → notifikasi muncul di status bar → tap → buka Inbox QR.
  - Fallback: jika WebSocket dan FCM gagal, Inbox QR melakukan polling ringan secara berkala.
  - Registrasi token FCM ke server saat login (`POST /devices/fcm-token`).
- Saat pesanan di-**Terima**: stok terpotong, masuk laporan, cetak struk dan tiket dapur.
- Saat pesanan di-**Tolak**: alasan dikirim ke server; jika memungkinkan, tampilkan ke halaman status pelanggan (P1).

**Selesai Bila:**
- Pesanan dari web QR meja muncul di Inbox QR semua perangkat kasir aktif dalam < 5 detik.
- Approval dan penolakan berjalan benar, stok terpotong setelah approval.
- Notifikasi muncul saat aplikasi di background.
- Kegagalan WebSocket atau FCM tidak menghilangkan pesanan dari Inbox.

---

### 💳 Fase 9 — QRIS Dinamis (Payment Gateway)

> ⚠️ **Prasyarat: Payment gateway (Midtrans/Xendit/DOKU) sudah dipilih dan merchant sudah terdaftar sebelum fase ini dimulai.**

**Yang dibangun:**
- Di web QR menu, pelanggan memilih metode bayar "QRIS". Aplikasi memanggil backend untuk membuat tagihan QRIS dinamis via gateway. Tampilkan QR code pembayaran dan countdown batas waktu bayar.
- **Di sisi Flutter (Inbox QR):**
  - Pesanan QRIS masuk dengan status `AWAITING_PAYMENT` — tidak perlu approval kasir.
  - Setelah webhook dikonfirmasi server → status berubah ke `APPROVED` secara otomatis → notifikasi realtime ke kasir → cetak struk dan tiket dapur.
  - Kasir tidak perlu mengkonfirmasi pembayaran QRIS dinamis secara manual.
- Tampilkan label "Lunas via QRIS" di struk.
- Refund QRIS melalui backend (dengan PIN Admin) — ditampilkan di UI sebagai status `REFUNDED` (P1).

**Selesai Bila:**
- Pesanan QRIS dari web QR berhasil diproses end-to-end di lingkungan sandbox gateway.
- Status pesanan berubah otomatis ke `APPROVED` di Inbox QR setelah pembayaran berhasil.
- Kasir tidak perlu melakukan aksi manual untuk pesanan QRIS yang sudah lunas.

---

### 🚀 Fase 10 — Kesiapan Produksi & Rilis

**Tujuan:** Memastikan aplikasi stabil, aman, dan siap dipakai di outlet sungguhan.

**Yang dibangun/diperiksa:**
- Uji di HP dan tablet Android nyata, berbagai merek, Android 7.0+, portrait dan landscape.
- Uji skenario online/offline campuran, batas sesi 7 hari, multi-perangkat bersamaan.
- Uji migrasi skema Drift: install versi lama → update ke versi baru → pastikan data tidak hilang.
- Pasang Crashlytics atau Sentry di aplikasi untuk pelacakan error.
- Panduan pengaturan HP kasir: matikan battery optimization untuk aplikasi, izin notifikasi, dsb.
- UAT bersama pemilik produk di outlet.
- Siapkan file APK / distribusi internal (Firebase App Distribution atau link langsung).

**Selesai Bila:**
- Semua fitur P0 lulus UAT tanpa defect kritis.
- Aplikasi stabil di minimal 3 merek HP Android berbeda.
- Panduan pengaturan HP kasir tersedia.

---

## 5. Dependensi Antar Fase (Diagram)

```
Fase 0 (Fondasi Flutter)
  └─ Fase 1 (Autentikasi & Role)
       └─ Fase 2 (Katalog Menu)
            └─ Fase 3 (Mesin Sync)
                 └─ Fase 4 (POS Kasir)
                      ├─ Fase 5 (Shift & Pengeluaran)
                      ├─ Fase 6 (Pesanan Online & Laporan)
                      └─ Fase 7 (Inventori & Resep)
                           └─ Fase 8 (Inbox QR & Notifikasi)
                                └─ Fase 9 (QRIS Dinamis)
                                     └─ Fase 10 (Produksi & Rilis)
```

---

## 6. Penyesuaian dengan Backend & Database

| Poin | Ketentuan |
| :--- | :--- |
| Base URL | Dapat diubah dari layar Login (disimpan di `flutter_secure_storage`) |
| Auth | JWT: access token (15 menit) + refresh token (7 hari). Auto-refresh via interceptor Dio |
| Format data | Uang: `int` (dalam sen atau rupiah bulat) untuk hindari float. Waktu: UTC dari server, tampilkan WIB |
| Sync | Gunakan endpoint `POST /sync/push` dan `GET /sync/pull?cursor=...` dari backend |
| UUID | Dibuat di perangkat menggunakan `uuid` package Flutter sebelum data dikirim ke server |
| Offline cache | Drift menyimpan semua tabel yang perlu offline (katalog, transaksi, shift, pengeluaran) |
| Role | Dibaca dari klaim JWT. Navigasi disesuaikan. Cache role di secure storage untuk mode offline |

---

## 7. Bagaimana Frontend & Backend Terhubung

Bagian ini menjelaskan secara konkret bagaimana Flutter (frontend) berkomunikasi dengan Flask (backend) dan kapan data mengalir ke mana.

---

### 7.1 Gambaran Besar Arsitektur

```
┌─────────────────────────────────────────────────────────┐
│                  PERANGKAT ANDROID                       │
│                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │  Flutter │───▶│  Drift       │───▶│  sync_outbox   │ │
│  │   UI     │    │  (SQLite     │    │  (antrian      │ │
│  │          │◀───│   lokal)     │◀───│   perubahan)   │ │
│  └──────────┘    └──────────────┘    └───────┬────────┘ │
│                                              │          │
│  ┌──────────────────────────────────────┐   │          │
│  │  Dio HTTP Client                     │   │          │
│  │  + Interceptor JWT (auto-refresh)    │◀──┘ Sync     │
│  └───────────────┬──────────────────────┘   Worker     │
└──────────────────│──────────────────────────────────────┘
                   │ HTTPS
                   ▼
┌─────────────────────────────────────────────────────────┐
│                  SERVER (Flask)                          │
│                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │  Nginx   │───▶│  Gunicorn    │───▶│  Blueprint     │ │
│  │ (proxy)  │    │  + Flask     │    │  Auth, Sync,   │ │
│  │          │    │  + JWT Guard │    │  Orders, dsb.  │ │
│  └──────────┘    └──────────────┘    └───────┬────────┘ │
│                                              │          │
│  ┌──────────────┐    ┌────────────────────┐  │          │
│  │  Redis       │    │  MySQL (produksi)  │◀─┘          │
│  │  (rate limit │    │  SQLite (testing)  │             │
│  │   + pub/sub) │    └────────────────────┘             │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

**Prinsip utama:**
- Flutter **menulis ke Drift lokal lebih dulu**, baru mengirim ke server.
- Server adalah **sumber kebenaran akhir** (master data server menang saat konflik).
- Semua request ke server **wajib membawa JWT** di header `Authorization: Bearer <token>` — kecuali endpoint publik (web QR menu).

---

### 7.2 Alur Token JWT (Login → Pakai → Refresh → Logout)

```
[1] LOGIN
  Flutter ──POST /auth/login──▶ Flask
         ◀── { access_token, refresh_token, user, role, device_id }
  Flutter menyimpan ke flutter_secure_storage:
    - access_token  (berlaku 15 menit)
    - refresh_token (berlaku 7 hari)
    - role, user_id, device_id (untuk navigasi & offline)

[2] SETIAP REQUEST
  Interceptor Dio otomatis menyisipkan header:
    Authorization: Bearer <access_token>

[3] TOKEN EXPIRED (server balas 401)
  Interceptor Dio mendeteksi 401
  ──POST /auth/refresh──▶ Flask (kirim refresh_token)
  ◀── { access_token baru }
  Simpan access_token baru, ulangi request awal secara otomatis.
  Pengguna tidak merasakan apapun (tidak perlu login ulang).

[4] REFRESH TOKEN EXPIRED (refresh juga ditolak)
  Hapus semua token dari secure storage
  Arahkan pengguna ke halaman Login
  Tampilkan pesan: "Sesi berakhir, silakan login kembali"

[5] LOGOUT
  ──POST /auth/logout──▶ Flask (server mencabut refresh token)
  Hapus semua token dan cache lokal
  Kembali ke halaman Login
```

> **Login Offline:** Jika tidak ada internet, bandingkan input password/PIN dengan **hash yang disimpan lokal** (disimpan saat login online terakhir). Sesi offline maksimal 7 hari dihitung dari login online terakhir.

---

### 7.3 Alur Sync (Flutter ↔ Flask)

Sync adalah jantung dari sistem offline-first. Ada dua arah: **Push** (lokal → server) dan **Pull** (server → lokal).

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PUSH: Kirim perubahan lokal ke server
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[A] Pengguna melakukan aksi (buat pesanan, tambah pengeluaran, dsb.)
    │
    ▼
[B] Flutter menulis ke tabel Drift lokal (mis. tabel `orders`)
    + menulis baris ke tabel `sync_outbox`:
      { id: UUID, entity: "order", payload: {...}, status: "pending" }
    │
    ▼
[C] Sync Worker terpicu (buka app / internet kembali / terjadwal)
    Ambil semua baris sync_outbox dengan status "pending"
    │
    ▼
[D] POST /sync/push  ──▶  Flask
    Body: { records: [ { idempotency_key, entity, payload }, ... ] }
    │
    ▼
[E] Flask memproses tiap record:
    - Jika idempotency_key sudah ada di server → abaikan (tidak duplikat)
    - Jika baru → simpan ke MySQL, isi server_version
    Balas: { processed: [...], errors: [...] }
    │
    ▼
[F] Flutter menghapus baris dari sync_outbox yang berhasil diproses
    Jika gagal → retry dengan exponential backoff (1s, 2s, 4s, ...)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULL: Ambil perubahan terbaru dari server
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[A] Flutter menyimpan nilai server_version terakhir yang diterima (mis. 1042)
    │
    ▼
[B] GET /sync/pull?cursor=1042  ──▶  Flask
    │
    ▼
[C] Flask mengembalikan semua record yang server_version-nya > 1042
    Balas: { records: [...], latest_version: 1098 }
    │
    ▼
[D] Flutter menerapkan perubahan ke Drift lokal (upsert berdasarkan UUID)
    Simpan latest_version = 1098 untuk pull berikutnya
    │
    ▼
[E] UI diperbarui secara reaktif via Riverpod (stream dari Drift)
```

**Kapan sync dipicu:**
| Pemicu | Jenis Sync |
|:---|:---|
| Aplikasi dibuka | Push + Pull |
| Koneksi internet kembali | Push + Pull |
| Setelah setiap transaksi selesai | Push |
| Tombol sync manual oleh pengguna | Push + Pull |
| WorkManager terjadwal (setiap N menit) | Push + Pull |

---

### 7.4 Endpoint Backend yang Dipakai Frontend

Ini adalah ringkasan endpoint utama yang perlu dipanggil Flutter. Detail lengkap ada di spesifikasi OpenAPI backend.

| Grup | Method | Endpoint | Siapa yang Memanggil | Keterangan |
|:---|:---|:---|:---|:---|
| **Auth** | POST | `/auth/login` | Semua | Login username+password atau PIN |
| | POST | `/auth/refresh` | Interceptor Dio | Perpanjang access token |
| | POST | `/auth/logout` | Semua | Cabut refresh token |
| | POST | `/auth/verify-pin` | Semua | Verifikasi PIN Admin untuk aksi sensitif |
| **Sync** | POST | `/sync/push` | Sync Worker | Kirim batch perubahan lokal |
| | GET | `/sync/pull` | Sync Worker | Ambil perubahan dari server sejak cursor |
| **Katalog** | GET | `/catalog` | Semua | Ambil katalog menu lengkap (varian + modifier) |
| | POST/PUT/DELETE | `/catalog/menus` | Admin | CRUD menu |
| | POST/PUT/DELETE | `/catalog/categories` | Admin | CRUD kategori |
| **Transaksi** | POST | `/orders` | Kasir | Buat pesanan (via sync, bukan langsung) |
| | GET | `/orders` | Kasir/Admin | Daftar pesanan dengan filter |
| | POST | `/orders/{id}/approve` | Kasir | Setujui pesanan QR |
| | POST | `/orders/{id}/reject` | Kasir | Tolak pesanan QR |
| **Shift** | POST | `/shifts/open` | Kasir | Buka shift baru |
| | POST | `/shifts/{id}/close` | Kasir | Tutup shift |
| | GET | `/shifts/current` | Kasir | Shift yang sedang aktif |
| **Pengeluaran** | GET/POST | `/expenses` | Kasir/Admin | Daftar dan tambah pengeluaran |
| **Laporan** | GET | `/reports/sales` | Kasir/Admin | Laporan penjualan (Kasir: tanpa laba) |
| | GET | `/reports/profit` | Admin only | Laporan laba kotor (Kasir → 403) |
| | GET | `/reports/charts` | Semua | Data grafik |
| **Inventori** | GET/POST/PUT | `/inventory/ingredients` | Admin | CRUD bahan baku |
| | GET/POST/PUT | `/inventory/recipes` | Admin | CRUD resep |
| | GET | `/inventory/stock-balances` | Admin | Saldo stok saat ini |
| **Perangkat** | POST | `/devices/fcm-token` | Semua | Daftarkan token FCM saat login |
| **Realtime** | WS | `ws://server/ws` | Semua | WebSocket untuk notifikasi pesanan QR |
| **Publik** | GET | `/public/tables/{token}/menu` | Web QR Menu | Katalog menu tanpa login |
| | POST | `/public/orders` | Web QR Menu | Buat pesanan dari web QR |

> **Catatan:** Semua endpoint non-publik wajib menyertakan header `Authorization: Bearer <access_token>`. Server akan menolak dengan `401` jika token tidak ada atau kedaluwarsa, dan `403` jika role tidak punya hak akses.

---

### 7.5 Bagaimana Data Mengalir untuk Transaksi POS (Contoh Konkret)

```
Kasir menekan "Bayar" di layar POS
│
├─[1] Flutter membuat UUID pesanan baru di perangkat
│
├─[2] Flutter menulis pesanan ke Drift lokal (tabel orders, order_items)
│       Status: APPROVED, payment_status: PAID
│       Selesai < 1 detik → UI langsung merespons
│
├─[3] Flutter menulis ke sync_outbox
│       { idempotency_key: <UUID pesanan>, entity: "order", payload: {...} }
│
├─[4] Flutter memotong stok bahan di Drift lokal sesuai resep
│       (tabel stock_movements, entry baru sebagai ledger)
│
├─[5] Flutter menampilkan pratinjau struk → kasir cetak via Bluetooth
│
└─[6] Sync Worker (di background) mengirim ke server
        POST /sync/push → Flask → MySQL
        Jika berhasil: hapus dari outbox
        Jika gagal: retry otomatis, data tetap aman di Drift lokal
```

Jika internet **tidak ada sama sekali** saat transaksi, langkah 6 ditunda sampai internet tersedia. Data tidak hilang karena sudah tersimpan di Drift lokal sejak langkah 2.

---

## 8. Checklist Verifikasi (Gunakan Sebelum Menyatakan Suatu Fase Selesai)

- [ ] Apakah semua aksi menulis ke Drift lokal lebih dulu sebelum mengirim ke server?
- [ ] Apakah layar tidak pernah menunggu server (tidak ada loading blocker untuk operasi kritis)?
- [ ] Apakah UUID dibuat di perangkat sebelum data ditulis ke lokal?
- [ ] Apakah navigasi dan komponen UI sudah menyesuaikan role pengguna?
- [ ] Apakah HPP dan laba tidak muncul sama sekali di UI Kasir (bukan hanya disembunyikan)?
- [ ] Apakah aksi sensitif (void, diskon besar, konfirmasi QRIS statis) memerlukan PIN Admin?
- [ ] Apakah layout POS tampil benar di HP (portrait) dan tablet (landscape dua panel)?
- [ ] Apakah indikator status sync menampilkan kondisi yang akurat?
- [ ] Apakah nilai uang ditampilkan dalam format Rupiah (bukan float mentah)?
- [ ] Apakah ada skenario offline yang diuji secara eksplisit (matikan WiFi, lakukan transaksi, nyalakan WiFi, cek sync)?
