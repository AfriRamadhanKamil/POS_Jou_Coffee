# PRD – POS Jou Coffee

Versi 2.0 · 16 November 2026 · Disusun ulang dari v1.4 menurut alur pengerjaan · Platform: Android (HP dan tablet) · Status: Siap dikerjakan tim implementasi

## 0. Cara Memakai Dokumen Ini

Dokumen ini ditujukan bagi programmer atau model AI yang mengimplementasikan aplikasi.

- Dokumen bersifat **high level**: menjelaskan apa yang dibangun, urutannya, dan aturan yang tidak boleh dilanggar. Detail teknis (nama kolom, daftar endpoint lengkap, tampilan layar) diputuskan implementer selama tidak melanggar aturan di dokumen ini.
- Kerjakan **fase secara berurutan** (Bagian 6). Jangan mulai fase berikutnya sebelum bagian "Selesai bila" pada fase sebelumnya terpenuhi.
- Prioritas: tanpa tanda = **P0** (wajib untuk rilis pertama). Bertanda **(P1)** = penting, dikerjakan setelah semua P0 di fase tersebut selesai.
- Aturan bisnis di Bagian 4 dan Bagian 7 tidak boleh diubah atau ditebak sendiri. Bila ada hal yang belum jelas, pakai asumsi default di Bagian 10 dan catat keputusannya.

## 1. Ringkasan Produk dan Tujuan

Jou Coffee POS adalah aplikasi kasir mobile untuk **satu outlet**. Aplikasi tetap bisa dipakai saat internet mati (offline-first) dan otomatis sinkron ke server saat online. Aplikasi mencakup POS kasir, pesanan online (GoFood dkk., input manual), QR menu untuk pelanggan, laporan, kas dan pengeluaran, serta manajemen menu, bahan baku, resep, dan stok.

**Masalah yang diselesaikan:**

- Transaksi tidak boleh berhenti saat internet putus.
- Pesanan GoFood/GrabFood/ShopeeFood dicatat terpisah dari kas dan laporan.
- Pelanggan antre di kasir hanya untuk memesan.
- Stok bahan baku tidak terpotong otomatis sehingga selisih sulit dilacak.
- Owner butuh batas hak akses yang jelas antara kasir dan pemilik.

**Metrik keberhasilan:**

| Tujuan | Target |
| --- | --- |
| Transaksi offline tersimpan sukses | 100% |
| Waktu dari tap Bayar sampai tersimpan lokal | < 1 detik |
| Transaksi hilang atau duplikat setelah sync | 0 |
| Porsi pesanan dine in lewat QR menu | ≥ 30% setelah 3 bulan |
| Median waktu approval pesanan QR oleh kasir | < 1 menit |
| Selisih stok sistem vs opname | < 5% |

## 2. Ruang Lingkup

**Masuk lingkup (versi ini):**

- Aplikasi kasir **Android: HP dan tablet** (portrait dan landscape), online dan offline.
- Tipe pesanan Dine In, Take Away, dan Delivery (Delivery hanya lewat platform seperti GoFood, diinput manual).
- QR menu untuk pelanggan (web ringan), dengan pembayaran tunai (approval kasir) dan QRIS dinamis.
- Laporan, grafik, kas/shift, pengeluaran.
- Manajemen menu, bahan baku, resep, stok, meja, dan pengguna.

**Di luar lingkup:** iOS, multi-outlet, integrasi API resmi GoFood/GrabFood/ShopeeFood, member dan voucher, integrasi akuntansi (lihat Bagian 12).

## 3. Teknologi dan Arsitektur

Alur umum: aplikasi Flutter menulis ke SQLite lokal, lalu worker sinkronisasi mengirim ke Flask REST API yang menyimpan ke MySQL. Notifikasi realtime lewat WebSocket dan FCM. QR menu adalah web ringan yang memakai API publik yang sama.

| Lapisan | Teknologi |
| --- | --- |
| Aplikasi | Flutter (Android HP dan tablet), Riverpod, go_router |
| Database lokal (offline) | SQLite via Drift |
| Jaringan dan sync | Dio, connectivity_plus, WorkManager (sync latar belakang Android) |
| Printer | Thermal Bluetooth ESC/POS 58/80 mm |
| Backend | Flask, SQLAlchemy, Alembic, Flask-JWT-Extended, Flask-SocketIO |
| Server | Gunicorn, Nginx, Redis (pub/sub realtime dan rate limit) |
| Database server | MySQL 8 |
| Notifikasi | FCM (push) dan WebSocket (saat aplikasi aktif) |
| QR menu | Web ringan (PWA), tanpa instal dan tanpa login |
| Pembayaran | Payment gateway dengan QRIS dinamis (provider belum dipilih) |

## 4. Aturan Utama (Wajib Dipatuhi di Semua Fase)

1. **Offline-first.** Semua aksi kasir menulis ke SQLite lebih dulu. Layar tidak pernah menunggu server. Sinkronisasi berjalan di latar belakang.
2. **ID dari perangkat.** Semua data memakai UUID yang dibuat di perangkat agar tidak bentrok saat offline. Nomor struk berformat kode perangkat, tanggal, urut (contoh: `JOU-K01-20261102-0007`).
3. **Sync idempoten.** Mengirim ulang data yang sama tidak boleh membuat duplikat. Tidak ada transaksi hilang atau ganda.
4. **Transaksi append-only.** Transaksi tidak pernah dihapus fisik. Koreksi dilakukan lewat void/refund baru. Master data memakai soft delete.
5. **Aturan konflik.** Master data: server menang. Dua perangkat memproses pesanan yang sama: yang pertama masuk ke server menang, perangkat lain diberi tahu.
6. **Stok berbasis ledger.** Stok dicatat sebagai pergerakan masuk/keluar (bukan angka yang ditimpa). Saldo dihitung server. Stok boleh minus dan ditandai untuk audit.
7. **Hak akses di server.** Izin divalidasi di server (RBAC lewat JWT). Menyembunyikan menu di aplikasi saja tidak cukup. Saat offline, izin dibaca dari cache lokal.
8. **Format data.** Uang memakai tipe desimal (bukan float). Waktu disimpan UTC dan ditampilkan WIB. Format Rupiah. Harga menu adalah harga akhir: **tanpa PPN dan service charge**.
9. **Pembayaran QR dipercaya dari server saja.** Total pesanan QR dihitung server. Status lunas QRIS hanya berubah dari webhook gateway yang terverifikasi, tidak pernah dari browser pelanggan.
10. **Aksi sensitif.** Void, refund, dan diskon di atas batas butuh PIN Admin. Aksi sensitif (void, hapus, ubah harga, ubah stok, ubah izin, konfirmasi QRIS statis) dicatat di audit log.
11. **UX kasir.** Bahasa Indonesia, tombol besar, dan konfirmasi untuk aksi kritis.

## 5. Peran dan Hak Akses

Hanya ada **tiga role**: Kasir, Admin/Owner, dan Super Admin.

| Area | Kasir | Admin/Owner | Super Admin |
| --- | --- | --- | --- |
| POS (Dine In, Take Away, pesanan online) dan approval pesanan QR | ✔ | ✔ | ✔ |
| Laporan penjualan | Lihat (tanpa HPP dan laba) | Lihat, ekspor, laba | Lihat, ekspor, laba |
| Grafik penjualan | Lihat | Lihat | Lihat |
| Kas dan shift | Lihat dan tambah | Lihat, tambah, rekonsiliasi | Lihat, tambah, rekonsiliasi |
| Pengeluaran | Lihat dan tambah | CRUD | CRUD |
| Menu, bahan baku, resep, stok, meja dan QR | ✖ | CRUD | CRUD |
| Akun Kasir | ✖ | CRUD | CRUD |
| Perangkat | ✖ | Kelola dan cabut | Kelola dan cabut |
| Akun Admin, pengaturan sistem, audit log | ✖ | ✖ | CRUD / ✔ |

**Catatan:**

- Hanya **1 akun Kasir**, yang boleh dipakai di beberapa perangkat (batas perangkat aktif bisa diatur).
- Kasir boleh melihat semua data laporan, pengeluaran, kas, dan grafik untuk semua tanggal, **kecuali HPP dan laba**.
- Kasir tidak bisa mengubah atau menghapus data yang sudah ada. Kasir hanya melihat menu sebagai katalog di layar POS, dan melihat label "Habis" bila stok tidak cukup.

## 6. Alur Pengerjaan (Fase)

| Fase | Nama | Hasil utama | Bergantung pada |
| --- | --- | --- | --- |
| 0 | Fondasi | Repo, CI, ERD, konvensi API, kerangka aplikasi | – |
| 1 | Autentikasi, Role, Perangkat | Login, role, perangkat terdaftar, login offline | 0 |
| 2 | Master Menu | CRUD menu, varian, modifier, channel, harga | 1 |
| 3 | Sinkronisasi | Sync engine dua arah dan indikator status | 2 |
| 4 | POS Kasir | Transaksi offline/online, bayar, cetak struk | 3 |
| 5 | Kas, Shift, Pengeluaran | Shift, kas masuk/keluar, pengeluaran | 4 |
| 6 | Pesanan Online, Laporan, Grafik | Delivery manual, laporan, grafik | 4, 5 |
| 7 | Inventori | Bahan, resep, stok, potong stok otomatis | 4 |
| 8 | QR Menu (Tunai) dan Notifikasi | QR meja, web menu, approval kasir | 3, 4, 7 |
| 9 | QRIS Dinamis | Pembayaran QRIS otomatis via gateway | 8 |
| 10 | Kesiapan Produksi | Uji lapangan, keamanan, backup, UAT, rilis | Semua |

Urutan adalah panduan pengerjaan, bukan estimasi jadwal.

### Fase 0 – Fondasi

**Tujuan:** menyiapkan dasar proyek agar fase berikutnya berjalan tanpa bongkar ulang.

- Siapkan repo untuk aplikasi Flutter dan API Flask, CI sederhana (lint dan test), serta lingkungan dev dan staging.
- Finalkan wireframe layar utama: Kasir (POS), Inbox QR, dan Inventori. Layout HP (portrait) dan tablet (landscape, POS dua panel).
- Finalkan ERD dengan 6 kelompok tabel: Akses, Katalog, Inventori, Transaksi, Keuangan, Sistem. Tabel yang disinkronkan punya kolom standar: id (UUID), created_at, updated_at, deleted_at, created_by, device_id, server_version (diisi server).
- Siapkan migrasi berversi untuk MySQL (Alembic) dan SQLite (Drift).
- Tetapkan konvensi API: prefiks `/api/v1`, JWT untuk semua endpoint non-publik, format error seragam, dan spesifikasi OpenAPI.
- Siapkan kerangka Flutter: state management, routing, lapisan data lokal, lapisan jaringan.

**Selesai bila:** CI berjalan, ERD dan OpenAPI awal disetujui, dan aplikasi kosong bisa dibuild ke HP dan tablet Android serta terhubung ke API.

### Fase 1 – Autentikasi, Role, dan Perangkat

**Tujuan:** setiap pengguna masuk dengan role yang benar dan perangkat yang terdaftar.

- Login username dan password. Kasir juga punya PIN 6 digit untuk masuk cepat. Access token berumur pendek (15 menit) plus refresh token.
- Tiga role melekat pada akun. Super Admin mengelola akun Admin. Admin mengelola akun Kasir.
- Perangkat terdaftar (device_id) saat login pertama. Jumlah perangkat aktif per akun dibatasi (configurable, default 3). Admin atau Super Admin bisa mencabut perangkat kapan saja.
- Login offline: password/PIN di-hash lokal. Sesi offline maksimal 7 hari (configurable), setelah itu wajib online.
- Navigasi aplikasi menyesuaikan role (lihat Bagian 5).
- Audit log dasar untuk aksi sensitif (P1).

**Selesai bila:** tiap role hanya melihat menu miliknya dan server menolak akses yang tidak berhak, perangkat yang dicabut tidak bisa login atau sync, dan sesi offline lebih dari 7 hari ditolak.

### Fase 2 – Master Menu (Katalog)

**Tujuan:** Admin bisa menyiapkan menu yang akan dijual.

- CRUD kategori, menu, varian, modifier (ukuran, es, gula, topping, dengan harga tambahan), dan foto.
- Channel penjualan (GoFood, GrabFood, ShopeeFood) dengan harga per channel dan komisi (%). Admin bisa menambah channel baru (P1).
- Endpoint katalog read-only untuk semua role (dipakai layar POS).
- Layar kelola menu hanya untuk Admin ke atas.

**Selesai bila:** Admin membuat menu lengkap, tersimpan di server, dan terbaca oleh akun Kasir.

### Fase 3 – Sinkronisasi Offline dan Online

**Tujuan:** membangun mesin sync sekali dan dipakai oleh semua fitur berikutnya.

- Aplikasi memakai antrean perubahan lokal (`sync_outbox`) dan worker latar belakang. Pemicu sync: aplikasi dibuka, koneksi kembali, setelah transaksi, tombol manual, dan terjadwal (WorkManager di Android).
- Backend menyediakan **push** (kirim batch, duplikat ditolak lewat idempotency key) dan **pull** (ambil perubahan sejak `server_version` terakhir).
- Retry dengan exponential backoff.
- Indikator status di UI: Online / Offline / Menyinkronkan / N data menunggu.
- Server mencatat waktu terima. Selisih jam perangkat lebih dari 5 menit ditandai.
- Retensi lokal: transaksi 90 hari terakhir. Data lebih lama hanya di server.
- Master data (menu dll.) di-pull ke SQLite agar katalog tersedia saat offline.

**Selesai bila:** katalog dari Fase 2 muncul di perangkat baru lalu tetap bisa dibuka saat internet mati, data uji yang dikirim berulang tidak membuat duplikat, dan indikator sync akurat.

### Fase 4 – POS Kasir (Offline dan Online)

**Tujuan:** kasir bisa berjualan penuh, termasuk tanpa internet.

- Katalog per kategori, pencarian, dan favorit. Pilih varian dan modifier.
- Tipe pesanan: Dine In (pilih nomor meja) dan Take Away. Delivery ditambahkan di Fase 6.
- Keranjang: ubah qty, catatan item, diskon manual per item atau per transaksi (nominal atau persen). Diskon di atas batas butuh PIN Admin.
- Metode bayar: **tunai** (hitung kembalian) dan **QRIS statis** (kasir mengonfirmasi uang masuk, tetap jalan offline, tercatat di audit log).
- Simpan (hold) pesanan dan lanjutkan nanti (P1).
- Cetak struk dan tiket dapur/bar lewat printer Bluetooth, serta cetak ulang struk. Siapkan fallback bagikan PDF.
- Void/refund dengan PIN Admin, dicatat sebagai transaksi koreksi baru (P1).
- Pesanan POS langsung berstatus APPROVED (lihat Bagian 7).
- Semua fitur P0 di fase ini berjalan 100% offline.

**Selesai bila:** serangkaian transaksi uji tanpa internet tersimpan semua (< 1 detik per transaksi), struk tercetak di 2–3 merek printer umum, dan setelah online semuanya terkirim tanpa duplikat.

### Fase 5 – Kas, Shift, dan Pengeluaran

**Tujuan:** uang di laci dan biaya operasional tercatat rapi.

- Buka shift (modal awal), kas masuk/keluar, dan tutup shift (hitung selisih). Admin bisa rekonsiliasi.
- Summary kas hanya menghitung pembayaran tunai berstatus PAID. QRIS dan Platform dicatat sebagai non-tunai.
- Pengeluaran: kategori, nominal, catatan, foto nota. Kategori dapat dikelola (sediakan API kategori pengeluaran). Kasir lihat dan tambah, Admin CRUD.
- Semua berjalan offline dan ikut tersinkron.

**Selesai bila:** shift bisa dibuka dan ditutup saat offline dengan selisih yang benar, serta pengeluaran baru tersimpan, tersinkron, dan muncul kembali setelah refresh.

### Fase 6 – Pesanan Online, Laporan, dan Grafik

**Tujuan:** semua penjualan, termasuk GoFood dkk., masuk satu laporan.

- Mode **Pesanan Online** di POS (tipe Delivery): pilih channel, input ID pesanan eksternal, item dengan harga per channel, dan komisi (%). Catat pendapatan kotor, komisi, dan bersih. Metode bayar "Platform" tidak masuk laci kas. Status: Diterima, Diproses, Siap, Diambil driver (P1).
- Laporan penjualan harian/mingguan/bulanan dengan filter tipe pesanan, channel, metode bayar, dan kasir. Termasuk laporan per channel.
- Grafik: penjualan per hari dan per jam, menu terlaris, per channel, per tipe pesanan.
- Laba kotor (pendapatan dikurangi HPP) hanya untuk Admin dan Super Admin (P1, butuh resep dari Fase 7).
- Ekspor PDF dan Excel (P1). Laporan bisa dibuka offline dari data lokal (P1).

**Selesai bila:** angka laporan cocok dengan transaksi uji POS dan online (per channel dan per metode bayar), dan Kasir tidak melihat HPP atau laba.

### Fase 7 – Inventori: Bahan Baku, Resep, Stok

**Tujuan:** stok bahan terpotong otomatis dan selisih bisa dilacak.

- Kelola satuan (sediakan API satuan) dan bahan baku (satuan, stok minimum, harga beli terakhir).
- Resep: menu/varian terhubung ke daftar bahan dan takaran. HPP dihitung otomatis.
- Stok masuk (pembelian), penyesuaian, waste, dan stok opname. Semuanya tercatat sebagai pergerakan stok.
- Stok terpotong otomatis sesuai resep saat transaksi POS. Void mengembalikan stok.
- Label "Habis" di POS bila stok tidak cukup, dan item bisa dinonaktifkan (P1). Notifikasi stok menipis (P1).
- Modul ini tidak terlihat oleh Kasir.

**Selesai bila:** menjual menu mengurangi bahan sesuai resep, dua perangkat offline yang menjual bahan yang sama tidak saling menimpa saat sync, dan stok opname menghasilkan koreksi yang tercatat.

### Fase 8 – QR Menu (Tunai) dan Notifikasi

**Tujuan:** pelanggan memesan sendiri dari HP-nya, kasir tinggal menyetujui.

- Admin mengelola meja dan membuat/mencetak QR per meja (token bertanda tangan, bisa di-regenerate).
- Web QR menu: pelanggan scan, melihat menu aktif tanpa login dan tanpa instal. Pilih Dine In (nomor meja terisi otomatis) atau Take Away (nama untuk dipanggil). Delivery tidak tersedia di QR menu.
- Pembayaran **tunai**: pesanan berstatus PENDING_APPROVAL. Semua perangkat kasir aktif menerima notifikasi (suara, push, badge). Kasir memilih **Terima**, **Tolak** (alasan wajib), atau **Edit** dulu (misalnya hapus item habis).
- Saat APPROVED: pesanan masuk laporan, stok terpotong, dan kasir mencetak nota serta tiket dapur. Lanjut PREPARING, READY, COMPLETED. Untuk tunai, kasir menerima uang dan menyerahkan nota langsung ke pelanggan.
- Halaman status untuk pelanggan, dengan nomor antrean atau nama.
- Server memeriksa ketersediaan menu saat checkout. Proteksi spam: rate limit per IP dan meja.
- Pesanan tunai tanpa respons kasir lebih dari N menit (default 10) menjadi EXPIRED dan pelanggan diarahkan ke kasir (P1).
- Notifikasi: FCM untuk push (butuh registrasi token perangkat) dan WebSocket saat aplikasi aktif. Bila push atau koneksi gagal, pesanan tetap muncul di Inbox QR saat refresh atau reconnect.
- QR menu butuh internet. Bila outlet offline, tampilkan pesan agar pelanggan memesan ke kasir.

**Selesai bila:** pesanan tunai dari HP pelanggan muncul di semua perangkat kasir aktif, bisa disetujui, masuk laporan dan stok, serta tercetak. Kegagalan push tidak menghilangkan pesanan.

### Fase 9 – QRIS Dinamis (Payment Gateway)

**Tujuan:** pelanggan membayar QRIS dari HP-nya dan pesanan otomatis diterima.

**Prasyarat:** payment gateway sudah dipilih dan merchant sudah terdaftar (Bagian 10).

- Di checkout QR menu, pelanggan bisa memilih **QRIS**. Server menghitung total, mengecek stok, lalu membuat tagihan QRIS dinamis lewat gateway dengan batas waktu bayar (status AWAITING_PAYMENT).
- Endpoint webhook publik (tanpa JWT): verifikasi tanda tangan gateway, cocokkan ID tagihan dan nominal, cek ulang status lewat API gateway, dan proses secara idempoten. Hasilnya pesanan **PAID dan APPROVED otomatis**, tanpa approval kasir.
- Tagihan yang tidak dibayar sampai batas waktu menjadi EXPIRED tanpa memengaruhi laporan dan stok. Server juga mengecek status tagihan secara berkala bila webhook telat.
- Refund lewat gateway bila pesanan dibatalkan setelah lunas (PIN Admin), dicatat sebagai REFUNDED (P1). Bila bahan ternyata habis setelah lunas, pesanan direfund.
- Rekonsiliasi harian antara laporan gateway dan data pembayaran, selisih ditandai.
- API key dan secret hanya di server. Sistem tidak pernah menyimpan data kartu atau e-wallet.
- Bangun lewat lapisan abstraksi provider agar gateway bisa diganti.
- Bila gateway bermasalah, pelanggan tetap bisa memilih Tunai.

**Selesai bila:** pembayaran uji berhasil end-to-end di sandbox lalu produksi, webhook palsu ditolak, webhook ganda tidak diproses dua kali, dan nominal serta referensi transaksi selalu cocok.

### Fase 10 – Kesiapan Produksi dan Rilis

**Tujuan:** memastikan aplikasi aman dan stabil dipakai di outlet sungguhan.

- Uji di HP dan tablet Android nyata (Android 7.0+), portrait dan landscape, termasuk beberapa merek HP untuk notifikasi dan battery optimization. Buat panduan pengaturan HP kasir.
- Uji skenario online/offline campuran, multi-perangkat, batas sesi offline 7 hari, dan upgrade migrasi SQLite pada tiap rilis.
- Uji keamanan (RBAC, rate limit, HTTPS) dan uji beban dasar.
- Pasang monitoring (Crashlytics atau Sentry di aplikasi, log sinkronisasi di server).
- Backup MySQL harian dan uji restore berkala.
- UAT di outlet bersama pemilik produk.

**Selesai bila:** seluruh fitur P0 lulus UAT, tidak ada defect kritis terbuka, serta prosedur backup, restore, dan dukungan operasional tersedia.

## 7. Referensi: Status Pesanan dan Aturan Laporan

| Atribut | Nilai |
| --- | --- |
| order.status | AWAITING_PAYMENT, PENDING_APPROVAL, APPROVED, PREPARING, READY, COMPLETED, REJECTED, EXPIRED, CANCELLED |
| order.payment_status | UNPAID, PAID, REFUNDED |
| order.source | POS, QR, ONLINE_PLATFORM |
| order.order_type | DINE_IN, TAKE_AWAY, DELIVERY |

**Alur status ringkas:**

- Pesanan POS dan pesanan online: langsung **APPROVED**.
- QR tunai: PENDING_APPROVAL, lalu APPROVED (diterima kasir), REJECTED (ditolak), atau EXPIRED.
- QR QRIS: AWAITING_PAYMENT, lalu APPROVED otomatis setelah lunas, atau EXPIRED.
- Setelah APPROVED: PREPARING, READY, COMPLETED.
- Batal setelah APPROVED menjadi CANCELLED dengan PIN Admin. Stok dan laporan dikoreksi lewat pergerakan lawan, bukan dengan menghapus data.

**Aturan laporan dan kas:**

- Laporan penjualan hanya menghitung order berstatus APPROVED ke atas yang tidak dibatalkan.
- AWAITING_PAYMENT dan PENDING_APPROVAL belum masuk laporan maupun stok.
- Summary kas hanya menghitung pembayaran tunai berstatus PAID.

## 8. Referensi: Gambaran Data dan API

**Kelompok data (MySQL di server, SQLite di perangkat untuk data yang perlu offline):**

- Akses: pengguna, perangkat, audit log
- Katalog: kategori, menu, varian, modifier, channel penjualan, harga per channel
- Inventori: satuan, bahan baku, resep, pergerakan stok, saldo stok, opname, pembelian
- Transaksi: meja, pesanan, item pesanan, pembayaran, log status pesanan
- Keuangan: kategori pengeluaran, pengeluaran, shift kas, pergerakan kas
- Sistem: notifikasi, pengaturan, perubahan sync

**Kelompok API (prefiks `/api/v1`, semua non-publik butuh JWT dan dicek izinnya di server):**

- Auth, Sync, Katalog, Inventori, Transaksi, Keuangan, Laporan, Pengguna dan Perangkat
- QR untuk kasir (daftar pesanan menunggu, terima, tolak)
- QR publik (menu, buat pesanan, status pesanan, buat tagihan QRIS, webhook gateway)
- Realtime (WebSocket dan registrasi token notifikasi perangkat)

Daftar endpoint dan skema rinci ditetapkan di spesifikasi OpenAPI pada Fase 0.

## 9. Kebutuhan Non-Fungsional

- **Performa:** aplikasi terbuka kurang dari 3 detik saat offline, katalog 500 menu tetap mulus, sync dalam batch (sekitar 200 record).
- **Keamanan:** HTTPS, hash password Argon2/bcrypt, access token 15 menit plus refresh token, RBAC di server, rate limit endpoint publik, validasi input, enkripsi SQLite (SQLCipher) opsional.
- **Keandalan:** sync idempoten, retry dengan backoff, transaksi tidak dihapus fisik, backup harian dan uji restore.
- **Kompatibilitas:** Android 7.0+ (API 24), HP dan tablet, portrait dan landscape.
- **UX:** bahasa Indonesia, tombol besar, format Rupiah, zona WIB.
- **Observability:** Crashlytics atau Sentry di aplikasi, log sinkronisasi di server.

## 10. Keputusan dan Asumsi Default

**Sudah diputuskan:**

- Fokus 1 outlet, platform Android (HP dan tablet) dulu, tanpa PPN dan service charge.
- Pembayaran hanya tunai dan QRIS. Di kasir: QRIS statis (dikonfirmasi manual, tetap jalan offline). Di QR menu: QRIS dinamis lewat payment gateway.
- QR menu bersifat opsional: pelanggan boleh memesan lewat QR atau langsung ke kasir.
- Delivery hanya lewat platform (diinput manual), tanpa kurir sendiri dan ongkir.
- Diskon manual saja. Member dan voucher belum ada.
- Kasir hanya 1 akun yang dipakai di beberapa perangkat.

**Masih terbuka (pakai asumsi default sampai dijawab):**

| Pertanyaan | Asumsi default |
| --- | --- |
| Merek dan tipe printer thermal | Bluetooth, mendukung ESC/POS, kertas 58 atau 80 mm. Uji 2–3 merek umum |
| Payment gateway mana (kandidat: Midtrans, Xendit, DOKU) dan kesiapan dokumen merchant | Belum ada default. **Fase 9 tidak dimulai sebelum gateway dipilih dan merchant terdaftar.** Urus pendaftaran paralel sejak awal |
| Apakah Kasir boleh melihat HPP dan laba | Tidak |

## 11. Risiko Utama

| Risiko | Mitigasi |
| --- | --- |
| Pendaftaran merchant gateway lambat sehingga Fase 9 tertunda | Mulai urus dokumen dan pemilihan gateway sejak Fase 0, bangun lewat abstraksi provider |
| Notifikasi QR tertunda karena battery optimization HP | WebSocket saat aplikasi aktif, FCM prioritas tinggi, Inbox QR sebagai cadangan, panduan pengaturan HP kasir |
| Stok minus karena sync tertunda | Stok berbasis ledger, tanda audit, rekonsiliasi lewat opname |
| Printer Bluetooth beragam merek | Uji 2–3 merek umum, siapkan fallback bagikan PDF |
| Kasir salah menandai QRIS statis sudah lunas | Kasir wajib cek notifikasi uang masuk, setiap konfirmasi tercatat di audit log |
| HP kasir hilang atau disalahgunakan | Perangkat terdaftar dan dibatasi, Admin bisa mencabut, setiap transaksi mencatat device_id, ganti password atau PIN |
| QR menu tidak bisa dipakai saat outlet offline | Tampilkan arahan ke kasir. Mode LAN lokal menjadi fase lanjut |
| Update aplikasi merusak skema SQLite | Migrasi Drift berversi dan uji upgrade di tiap rilis |

## 12. Fase Lanjut (Di Luar Versi Ini)

- **iOS:** perlu pengujian ulang sync latar belakang dan notifikasi, karena batasan platform berbeda dari Android.
- **Multi-outlet:** menambah `outlet_id` di semua data dan migrasi di server serta semua perangkat. Perkiraan kasar 3–4 sprint tambahan.
- **Integrasi API resmi** GoFood, GrabFood, dan ShopeeFood (butuh kemitraan).
- **Member dan voucher**, serta integrasi akuntansi.
- **Mode LAN lokal** untuk QR menu saat internet outlet mati.
