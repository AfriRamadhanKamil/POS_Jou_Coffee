# PRD – POS Jou Coffee

Versi 1.4 (fokus 1 outlet) · 11 November 2026 · Revisi kebutuhan dan kesiapan produksi frontend · Status: Draft untuk review

## 1. Ringkasan Produk

Jou Coffee POS adalah aplikasi kasir mobile (Flutter) untuk satu outlet yang tetap bisa dipakai saat internet mati (offline-first) dan otomatis sinkron ke server saat online. Backend memakai Flask (asumsi: “flash” = Flask, Python) dengan MySQL di server dan SQLite di perangkat. Aplikasi mencakup POS kasir, pesanan online (GoFood dkk.), QR menu untuk pelanggan, laporan, kas dan pengeluaran, serta manajemen menu, bahan baku, resep, dan stok. Hanya ada tiga role: **Kasir**, **Admin/Owner**, dan **Super Admin**.

### Masalah yang diselesaikan

- Transaksi tidak boleh berhenti saat internet putus.
- Pesanan GoFood/GrabFood/ShopeeFood sering dicatat terpisah dari kas dan laporan.
- Pelanggan antre di kasir hanya untuk memesan, dan kasir kerepotan mencatat.
- Stok bahan baku tidak terpotong otomatis sehingga selisih sulit dilacak.
- Owner butuh batas hak akses yang jelas antara kasir dan pemilik.

## 2. Tujuan dan Metrik Keberhasilan

| Tujuan | Metrik | Target |
| --- | --- | --- |
| Kasir tetap jualan tanpa internet | Transaksi offline tersimpan sukses | 100% |
| Transaksi cepat | Waktu dari tap Bayar sampai tersimpan (lokal) | < 1 detik |
| Data aman saat sinkron | Transaksi hilang atau duplikat setelah sync | 0 |
| Antrean berkurang | Porsi pesanan dine in lewat QR menu | ≥ 30% setelah 3 bulan |
| Respon kasir cepat | Median waktu approval pesanan QR | < 1 menit |
| Stok akurat | Selisih stok sistem vs opname | < 5% |

## 3. Ruang Lingkup dan Asumsi

**Masuk lingkup:** POS offline/online, tipe pesanan (Dine In, Take Away, Delivery), pesanan online manual, QR menu (pembayaran tunai dengan approval kasir, QRIS dengan auto-terima setelah lunas), laporan, pengeluaran, kas/shift, grafik penjualan, manajemen menu, bahan baku, resep, stok, manajemen pengguna, sinkronisasi offline-online.

**Di luar lingkup (fase lanjut):** multi-outlet (hanya gambaran di Lampiran A), integrasi API resmi GoFood/GrabFood/ShopeeFood, member dan voucher (konsep dari klien belum ada), dan integrasi akuntansi. Aplikasi mobile ditargetkan untuk Android dan iOS; dukungan sinkronisasi latar belakang harus mengikuti batasan masing-masing platform.

**Asumsi yang dipakai dokumen ini:**

- Aplikasi kasir mendukung Android dan iOS pada HP/tablet. Fokus 1 outlet: tidak ada fitur multi-outlet di versi ini (gambaran multi-outlet ada di Lampiran A, hanya sebagai referensi). Tidak ada PPN dan service charge, harga menu adalah harga akhir.
- Printer struk thermal 58/80 mm via Bluetooth (ESC/POS).
- Pesanan GoFood dkk. di tahap awal diinput manual oleh kasir, karena API resmi mereka butuh kemitraan.
- QR menu membutuhkan internet di sisi server dan kasir, karena pelanggan memakai HP sendiri.
- Pembayaran pesanan QR: tunai dibayar ke kasir, QRIS dibayar langsung oleh pelanggan lewat payment gateway (QRIS dinamis). Di kasir, QRIS memakai QRIS statis yang dikonfirmasi manual oleh kasir sehingga tetap bisa dipakai saat offline.

## 4. Peran dan Hak Akses

- **Kasir:** operasional harian (transaksi, approval QR, kas, pengeluaran).
- **Admin/Owner:** semua fitur operasional ditambah manajemen menu, stok, resep, laporan lengkap, dan akun kasir.
- **Super Admin:** pengelola sistem. Semua akses Admin ditambah akun Admin, pengaturan sistem, perangkat, dan audit log.

| Fitur | Kasir | Admin/Owner | Super Admin |
| --- | --- | --- | --- |
| POS offline (Dine In, Take Away, Delivery) | ✔ | ✔ | ✔ |
| POS pesanan online (GoFood dkk.) | ✔ | ✔ | ✔ |
| Approval pesanan QR | ✔ | ✔ | ✔ |
| Laporan penjualan | Lihat | Lihat, ekspor, laba | Lihat, ekspor, laba |
| Pengeluaran | Lihat + tambah | Tambah, ubah, hapus | Tambah, ubah, hapus |
| Summary kas | Lihat + tambah (shift, kas masuk/keluar) | Lihat, tambah, rekonsiliasi | Lihat, tambah, rekonsiliasi |
| Grafik penjualan | Lihat | Lihat | Lihat |
| Menu | ✖ | CRUD | CRUD |
| Bahan baku | ✖ | CRUD | CRUD |
| Resep | ✖ | CRUD | CRUD |
| Stok (masuk, opname, waste) | ✖ | CRUD | CRUD |
| Meja dan QR | ✖ | CRUD | CRUD |
| Akun kasir | ✖ | CRUD | CRUD |
| Akun Admin/Owner | ✖ | ✖ | CRUD |
| Pengaturan sistem, perangkat, audit log | ✖ | Perangkat saja | ✔ |

**Catatan hak akses:**

- Menu di layar POS hanya katalog untuk memilih item. Kasir tidak melihat modul Menu, Bahan Baku, Resep, dan Stok. Kasir hanya melihat label “Habis” bila stok tidak cukup.
- Laporan untuk kasir tidak menampilkan HPP dan laba, karena datanya berasal dari resep dan bahan baku. Kasir hanya 1 akun yang bisa dipakai di beberapa perangkat, dan boleh melihat semua data laporan, pengeluaran, kas, dan grafik untuk semua tanggal.
- Kasir tidak bisa mengubah atau menghapus data. Void, refund, dan diskon di atas batas tertentu butuh PIN Admin (usulan).
- Izin divalidasi di server (RBAC lewat klaim JWT), bukan hanya dengan menyembunyikan menu di Flutter. Saat offline, izin dibaca dari cache lokal.

## 5. Arsitektur dan Teknologi

Alur umum: aplikasi Flutter menulis ke SQLite lokal, lalu worker sinkronisasi mengirim ke Flask REST API yang menyimpan ke MySQL. Notifikasi realtime lewat WebSocket dan FCM. QR menu adalah web ringan yang bicara ke API publik yang sama.

| Lapisan | Teknologi | Alasan |
| --- | --- | --- |
| Mobile | Flutter 3.x, Riverpod, go_router | State management jelas, mudah dites |
| DB lokal | SQLite via Drift | Relasional, migrasi versi, transaksi atomik |
| Jaringan | Dio, connectivity_plus, WorkManager | Retry dan sync di latar belakang |
| Printer | print_bluetooth_thermal, esc_pos_utils | Struk dan tiket dapur |
| Grafik | fl_chart | Grafik native Flutter |
| Notifikasi | FCM + WebSocket (saat app aktif) | Push untuk pesanan QR; WebSocket menjadi pembaruan realtime saat aplikasi aktif |
| Backend | Flask, SQLAlchemy, Alembic, Flask-JWT-Extended, Marshmallow, Flask-SocketIO | Ringan dan cocok dengan MySQL |
| Server | Gunicorn (gevent), Nginx, Redis | Redis untuk pub/sub SocketIO dan rate limit |
| DB server | MySQL 8 (InnoDB, utf8mb4) | Sesuai kebutuhan Anda |
| QR menu | Web ringan (PWA) | Pelanggan tanpa instal aplikasi |
| Pembayaran | Payment gateway dengan QRIS dinamis (contoh: Midtrans, Xendit, DOKU) | Status lunas otomatis lewat webhook, tanpa menyimpan data pembayaran sendiri |

## 6. Strategi Offline-First dan Sinkronisasi

Prinsip: semua aksi kasir menulis ke SQLite dulu, sinkronisasi berjalan di latar belakang. Layar tidak pernah menunggu server.

| Aspek | Keputusan |
| --- | --- |
| ID data | UUID dibuat di perangkat (CHAR(36)) sehingga tidak bentrok saat offline |
| Nomor struk | Prefiks kode perangkat, tanggal, urut. Contoh: JOU-K01-20261102-0007 |
| Push | Tabel sync_outbox (entitas, operasi, payload, idempotency_key, retry). Dikirim batch ke POST /sync/push. Server menolak duplikat lewat idempotency_key |
| Pull | GET /sync/pull?cursor=N. Server mengirim perubahan sejak server_version terakhir |
| Konflik master data | Server menang (last-write-wins berdasarkan server_version) |
| Konflik transaksi | Tidak ada, karena transaksi append-only. Koreksi lewat void/refund baru |
| Stok | Disimpan sebagai ledger stock_movements (delta plus/minus). Saldo dihitung server sehingga dua kasir offline tidak saling menimpa. Stok boleh minus dan ditandai untuk audit |
| Login offline | PIN/password di-hash lokal. Sesi offline maksimal 7 hari (configurable), setelah itu wajib online; penerapan dan pengujian batas sesi wajib selesai sebelum rilis |
| Pemicu sync | App dibuka, koneksi kembali, setelah transaksi, tombol manual; Android juga mencoba sync terjadwal. iOS memakai background refresh best-effort dan sync saat aplikasi aktif karena jadwal background tidak dijamin OS |
| Indikator | Online / Offline / Menyinkronkan / N data menunggu |
| Jam perangkat | Server mencatat waktu terima. Selisih lebih dari 5 menit ditandai |
| Retensi lokal | Transaksi 90 hari terakhir. Sisanya hanya di server |
| QRIS | Di QR menu, tagihan QRIS dibuat oleh server sehingga hanya tersedia saat online. QRIS statis di kasir dikonfirmasi manual dan tetap jalan offline |

## 7. Kebutuhan Fungsional

Prioritas: P0 = wajib rilis pertama, P1 = penting, P2 = nanti.

### 7.1 Autentikasi dan Pengguna

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-A1 | Login username dan password. Kasir juga punya PIN 6 digit untuk masuk cepat | P0 |
| FR-A2 | Hanya 3 role, melekat pada akun | P0 |
| FR-A3 | Super Admin membuat/menonaktifkan Admin. Admin mengelola akun Kasir (hanya 1 akun) | P0 |
| FR-A4 | Akun Kasir bisa login di beberapa perangkat. Perangkat terdaftar (device_id) saat login pertama dan jumlah perangkat aktif dibatasi (configurable, usulan default 3). Admin atau Super Admin bisa mencabut perangkat kapan saja, termasuk bila HP rusak atau hilang | P0 |
| FR-A5 | Audit log untuk aksi sensitif (void, hapus, ubah harga, ubah stok, ubah izin) | P1 |
| FR-A6 | Aman untuk banyak perangkat: bila dua perangkat menyetujui atau mengubah pesanan yang sama, server memutuskan (yang pertama masuk menang) dan perangkat lain diberi tahu | P0 |

### 7.2 POS (Offline dan Online)

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-P1 | Katalog per kategori, pencarian, dan favorit | P0 |
| FR-P2 | Varian dan modifier (ukuran, es, gula, topping) dengan harga tambahan | P0 |
| FR-P3 | Tipe pesanan: Dine In (pilih nomor meja), Take Away, Delivery (lewat platform seperti GoFood, pilih channel) | P0 |
| FR-P4 | Keranjang: ubah qty, catatan item, diskon manual per item atau per transaksi (nominal atau persen), tanpa PPN dan service charge | P0 |
| FR-P5 | Metode bayar: tunai (hitung kembalian) dan QRIS statis (kasir mengonfirmasi pembayaran masuk, tetap jalan saat offline) | P0 |
| FR-P6 | Simpan (hold) pesanan dan lanjutkan nanti | P1 |
| FR-P7 | Cetak struk Bluetooth dan tiket dapur/bar, cetak ulang struk | P0 |
| FR-P8 | Void/refund dengan PIN Admin. Stok dikembalikan otomatis | P1 |
| FR-P9 | Seluruh fitur P0 di modul ini berjalan 100% offline | P0 |
| FR-P10 | Item yang stoknya habis diberi label dan bisa dinonaktifkan | P1 |

### 7.3 Pesanan Online (GoFood, GrabFood, ShopeeFood, dll.)

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-O1 | Mode “Pesanan Online” di POS dengan pilihan channel | P0 |
| FR-O2 | Input ID pesanan eksternal, item, harga per channel (price list terpisah), dan komisi (%) | P0 |
| FR-O3 | Catat pendapatan kotor, komisi, dan bersih. Metode bayar “Platform” tidak masuk laci kas | P0 |
| FR-O4 | Admin bisa menambah channel baru | P1 |
| FR-O5 | Status: Diterima, Diproses, Siap, Diambil driver | P1 |
| FR-O6 | Laporan per channel | P0 |

### 7.4 QR Menu

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-Q1 | Admin membuat dan mencetak QR per meja (token unik, bisa di-regenerate) | P0 |
| FR-Q2 | Pelanggan scan lalu melihat menu aktif tanpa login dan tanpa instal | P0 |
| FR-Q3 | Pilih tipe: Dine In (nomor meja terisi otomatis) atau Take Away (nama untuk dipanggil). Delivery tidak tersedia di QR menu karena hanya lewat platform | P0 |
| FR-Q4 | Tunai: pesanan berstatus Menunggu Persetujuan dan semua perangkat kasir yang aktif menerima notifikasi suara, push, dan badge. QRIS: pesanan berstatus Menunggu Pembayaran sampai lunas | P0 |
| FR-Q5 | Khusus pesanan tunai: kasir bisa Terima, Tolak (alasan wajib), atau edit dulu (misal hapus item habis) sebelum terima. Pesanan QRIS tidak butuh approval, otomatis diterima setelah lunas | P0 |
| FR-Q6 | Setelah diterima (tunai: disetujui kasir, QRIS: otomatis setelah lunas), pesanan otomatis masuk laporan dan stok berkurang sesuai resep. Kasir mencetak nota dan tiket dapur | P0 |
| FR-Q7 | Halaman status pelanggan: Menunggu Pembayaran atau Menunggu Persetujuan, Diterima, Diproses, Siap. Ada nomor antrean atau nama untuk dipanggil | P0 |
| FR-Q8 | Pesanan tunai tanpa respons kasir, atau tagihan QRIS yang tidak dibayar, lebih dari N menit (default 10) menjadi Kedaluwarsa dan pelanggan diarahkan ke kasir | P1 |
| FR-Q9 | Proteksi spam: rate limit per IP dan meja, token meja bertanda tangan | P0 |
| FR-Q10 | Kasir menandai Siap dan Selesai. Untuk tunai, kasir mencatat uang diterima dan menyerahkan nota langsung ke pelanggan | P0 |
| FR-Q11 | Di checkout pelanggan memilih metode bayar: Tunai atau QRIS | P0 |
| FR-Q12 | QRIS: tagihan QRIS dinamis lewat payment gateway. Status lunas hanya dipercaya dari webhook yang terverifikasi (Lampiran B) | P0 |
| FR-Q13 | Server memeriksa ketersediaan menu saat checkout sebelum tagihan dibuat, karena pesanan QRIS tidak melewati approval kasir | P0 |
| FR-Q14 | Refund QRIS lewat gateway bila pesanan dibatalkan setelah lunas (PIN Admin) | P1 |
| FR-Q15 | Notifikasi pesanan QR dikirim ke perangkat kasir; bila push atau koneksi realtime tidak tersedia, aplikasi tetap menampilkan pesanan saat refresh/reconnect | P0 |

### 7.5 Laporan, Pengeluaran, Kas, dan Grafik

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-R1 | Laporan penjualan harian/mingguan/bulanan dengan filter tipe pesanan, channel, metode bayar, kasir. Kasir hanya lihat | P0 |
| FR-R2 | Pengeluaran: kategori, nominal, catatan, foto nota. Kasir lihat dan tambah, Admin CRUD | P0 |
| FR-R3 | Summary kas: buka shift (modal awal), kas masuk/keluar, tutup shift (hitung selisih) | P0 |
| FR-R4 | Grafik: penjualan per hari dan jam, menu terlaris, per channel, per tipe pesanan | P0 |
| FR-R5 | Laba kotor (pendapatan dikurangi HPP dari resep), hanya Admin/Owner dan Super Admin | P1 |
| FR-R6 | Ekspor PDF dan Excel | P1 |
| FR-R7 | Laporan bisa dibuka offline dari data lokal | P1 |
| FR-R8 | Pengeluaran memiliki kategori yang dapat dikelola dan dicatat melalui API | P0 |

### 7.6 Manajemen (Admin/Owner dan Super Admin)

| ID | Kebutuhan | Prioritas |
| --- | --- | --- |
| FR-M1 | CRUD menu dan kategori, varian, modifier, harga per channel, foto | P0 |
| FR-M2 | CRUD bahan baku: satuan, stok minimum, harga beli terakhir | P0 |
| FR-M3 | Resep (BOM): menu/varian ke daftar bahan dan takaran. HPP dihitung otomatis | P0 |
| FR-M4 | Stok masuk (pembelian), penyesuaian, waste, dan stok opname | P0 |
| FR-M5 | Pengurangan stok otomatis sesuai resep saat transaksi POS atau approval QR | P0 |
| FR-M6 | Notifikasi stok menipis | P1 |
| FR-M7 | Kelola meja, QR, dan akun kasir | P0 |
| FR-M8 | Super Admin: akun Admin, pengaturan sistem (template struk, batas diskon), perangkat, audit log | P1 |
| FR-M9 | Admin mengelola satuan bahan baku serta melakukan pembelian dan stok opname melalui alur yang tercatat | P0 |

## 8. Alur QR Menu dan Status Pesanan

- Pelanggan scan QR meja dan menu terbuka. QR menu bersifat opsional, pelanggan juga boleh memesan langsung ke kasir.
- Pelanggan memilih menu dan tipe pesanan (Dine In atau Take Away). Server memeriksa ketersediaan menu.
- Di checkout pelanggan memilih metode bayar:
- **QRIS:** server membuat tagihan QRIS dinamis (status **AWAITING_PAYMENT**). Setelah pelanggan membayar dan webhook gateway terverifikasi, pesanan otomatis **APPROVED** dengan payment_status **PAID**.
- **Tunai:** status **PENDING_APPROVAL**. Perangkat kasir menerima notifikasi (FCM dan WebSocket), lalu kasir memilih Terima, Tolak, atau Edit. Jika diterima, status **APPROVED**.
- Saat APPROVED, pesanan masuk laporan dan stok dipotong sesuai resep (stock_movements tipe SALE). Perangkat kasir menerima notifikasi dan kasir mencetak nota dan tiket dapur.
- Barista memproses (**PREPARING**), lalu **READY**. Pelanggan menunggu di meja atau dipanggil kasir.
- Tunai: kasir menerima uang dan menyerahkan nota langsung ke pelanggan (UNPAID menjadi PAID). QRIS sudah lunas sejak awal. Setelah pesanan diterima pelanggan, status **COMPLETED**.
- Jika dibatalkan setelah APPROVED: **CANCELLED/VOID** dengan PIN Admin. Stok dan laporan dikoreksi lewat movement lawan, bukan dengan menghapus data. Pesanan QRIS yang sudah lunas direfund lewat gateway.

| Atribut | Nilai |
| --- | --- |
| order.status | AWAITING_PAYMENT, PENDING_APPROVAL, APPROVED, PREPARING, READY, COMPLETED, REJECTED, EXPIRED, CANCELLED |
| order.payment_status | UNPAID, PAID, REFUNDED |
| order.source | POS, QR, ONLINE_PLATFORM |
| order.order_type | DINE_IN, TAKE_AWAY, DELIVERY |

Aturan laporan: pesanan POS langsung berstatus APPROVED. Laporan penjualan menghitung order berstatus APPROVED ke atas yang tidak dibatalkan. Pesanan AWAITING_PAYMENT dan PENDING_APPROVAL belum masuk laporan maupun stok. Summary kas hanya menghitung pembayaran tunai berstatus PAID sebagai kas laci, sedangkan QRIS dan Platform dicatat sebagai non-tunai.

## 9. Desain Database (MySQL)

**Kolom standar tabel yang disinkronkan:** id CHAR(36) PK, created_at, updated_at, deleted_at (soft delete), created_by, device_id, server_version BIGINT (diisi server). Uang memakai DECIMAL(15,2), kuantitas stok DECIMAL(15,4), semua waktu disimpan UTC.

| Kelompok | Tabel |
| --- | --- |
| Akses | users (role: kasir/admin/super_admin), devices, audit_logs |
| Katalog | categories, menus, menu_variants, modifier_groups, modifiers, sales_channels, menu_channel_prices |
| Inventori | units, ingredients, recipes, recipe_items, stock_movements (ledger), stock_balances, stock_opnames, stock_opname_items, purchases, purchase_items |
| Transaksi | tables, orders, order_items, order_item_modifiers, payments, order_status_logs |
| Keuangan | expense_categories, expenses, cash_shifts, cash_movements |
| Sistem | notifications, settings, sync_changes (server), sync_outbox (hanya SQLite) |

**Kolom penting tabel orders:** order_no (unik), source, order_type, table_id, channel_id, external_order_id, status, payment_status, subtotal, discount, platform_commission, total, customer_name, shift_id, approved_by, approved_at.

**Indeks utama:** (created_at), (status), (server_version), unique(order_no), unique(idempotency_key).

## 10. Daftar Endpoint API

Prefiks /api/v1. Semua endpoint non-publik butuh JWT dan dicek izinnya di server. Daftar berikut adalah kontrak API yang dibutuhkan produk, bukan pernyataan bahwa semua endpoint sudah tersedia di backend saat ini. Gap implementasi yang diketahui dirangkum pada bagian 13.

| Grup | Endpoint |
| --- | --- |
| Auth | POST /auth/login, /auth/refresh, /auth/logout, /auth/verify-pin |
| Sync | POST /sync/push, GET /sync/pull |
| Katalog | GET /menus/catalog (semua role, read-only untuk POS). CRUD /menus, /categories, /modifiers, /channels (Admin ke atas) |
| Inventori | GET /units. CRUD /ingredients, /recipes, /purchases. POST /stock/movements, /stock/opname (Admin ke atas) |
| Transaksi | POST /orders, PATCH /orders/{id}/status, POST /orders/{id}/payments, POST /orders/{id}/void |
| QR (kasir) | GET /orders/pending-approval, POST /orders/{id}/approve, POST /orders/{id}/reject |
| QR (publik) | GET /public/qr/{token}/menu, POST /public/qr/{token}/orders, GET /public/orders/{id}/status, POST /public/orders/{id}/pay (buat tagihan QRIS), POST /public/payments/webhook (dari gateway) |
| Keuangan | GET /expense-categories; CRUD /expense-categories untuk Admin ke atas. GET dan POST /expenses, /shifts, /cash-movements. PATCH dan DELETE hanya Admin ke atas |
| Laporan | GET /reports/sales, /reports/cash-summary, /reports/charts, /reports/profit (Admin ke atas) |
| Pengguna | /users (Admin: kasir, Super Admin: semua), /devices (daftar dan cabut perangkat), /audit-logs (Super Admin) |
| Realtime | WebSocket /ws, channel orders; POST dan DELETE /devices/push-token untuk registrasi token notifikasi perangkat |

## 11. Kebutuhan Non-Fungsional

- **Performa:** app terbuka kurang dari 3 detik saat offline, katalog 500 menu tetap mulus, sync batch 200 record.
- **Keamanan:** HTTPS, hash password Argon2/bcrypt, access token 15 menit plus refresh token, RBAC di server, SQLite terenkripsi (SQLCipher) opsional, rate limit endpoint publik, validasi input.
- **Keandalan:** sync idempoten, retry dengan exponential backoff, data transaksi tidak pernah dihapus fisik, backup MySQL harian dan uji restore berkala.
- **Kompatibilitas:** Android 7.0+ (API 24) dan iOS (versi minimum ditetapkan sebelum rilis), HP dan tablet, portrait dan landscape.
- **UX:** bahasa Indonesia, tombol besar untuk kasir, konfirmasi untuk aksi kritis, format Rupiah dan zona WIB.
- **Observability:** Crashlytics/Sentry di app, log sinkronisasi di server.
- **Notifikasi dan background:** push notification harus diuji pada Android dan iOS. Sinkronisasi iOS di latar belakang bersifat best-effort; aplikasi wajib tetap melakukan sync saat dibuka, koneksi pulih, dan atas permintaan pengguna.

## 12. Navigasi Aplikasi per Role

| Role | Menu utama |
| --- | --- |
| Kasir | Kasir (POS), Pesanan (termasuk Inbox QR dengan badge), Laporan (lihat), Kas dan Pengeluaran, Akun |
| Admin/Owner | Semua menu Kasir, ditambah Inventori (Menu, Bahan Baku, Resep, Stok), Meja dan QR, Pengguna, Perangkat, Pengaturan |
| Super Admin | Semua menu Admin, ditambah Audit Log dan Konfigurasi Sistem |

## 13. Roadmap dan Kesiapan Produksi

Roadmap berikut mengelompokkan pekerjaan menurut kapabilitas produk. Fitur frontend yang sudah tersedia belum berarti backend, kredensial layanan eksternal, dan proses operasionalnya siap produksi.

| Fase | Sprint | Isi |
| --- | --- | --- |
| 0. Fondasi | S1 | Setup repo dan CI, desain UI/UX, ERD final, skema Drift dan Alembic |
| 1. MVP Kasir | S2–S6 | Auth dan role, master menu, POS offline, printer, sync engine, shift dan kas, pengeluaran |
| 2. Online dan Laporan | S7–S9 | Pesanan online (GoFood dkk.), laporan, grafik penjualan |
| 3. Inventori | S10–S12 | Bahan baku, resep, stok, pemotongan otomatis, opname |
| 4. QR Menu | S13–S16 | QR per meja, web menu, notifikasi, approval kasir (tunai), pembayaran QRIS dinamis lewat gateway, tracking pelanggan |
| 5. Kesiapan Produksi | Setelah fitur inti | Selesaikan gap backend dan integrasi di bawah, uji Android/iOS dan perangkat outlet, UAT, backup/restore, keamanan, monitoring, dan persiapan rilis |

Urutan fase adalah panduan, bukan estimasi jadwal. Rilis produksi hanya dilakukan setelah seluruh kriteria P0 pada tabel kesiapan produksi terpenuhi.

### 13.1 Backlog kesiapan produksi

| Area | Pekerjaan yang harus diselesaikan | Kriteria selesai | Prioritas |
| --- | --- | --- | --- |
| QRIS dinamis | Pilih dan daftarkan merchant ke payment gateway; implementasikan pembuatan tagihan, verifikasi webhook, idempotensi, kedaluwarsa, rekonsiliasi, dan alur refund di backend | Pembayaran uji berhasil end-to-end di sandbox dan produksi; status lunas hanya berasal dari notifikasi gateway terverifikasi; nominal dan referensi transaksi cocok | P0 |
| Notifikasi pesanan QR | Konfigurasikan Firebase Cloud Messaging, token perangkat, izin notifikasi, dan penanganan notifikasi pada aplikasi | Pesanan baru memberi notifikasi pada perangkat yang terdaftar; kegagalan push tidak menghilangkan pesanan dari inbox dan status dapat diperbarui saat reconnect | P0 |
| Sinkronisasi iOS | Uji sync saat aplikasi aktif, kembali ke foreground, koneksi pulih, serta background refresh best-effort; dokumentasikan batasan iOS | Transaksi antrean tetap tersimpan dan terkirim tanpa duplikasi; UI menunjukkan status antrean dan menyediakan sync manual | P0 |
| API kategori pengeluaran | Sediakan endpoint baca/tulis kategori pengeluaran dan pastikan endpoint pembuatan pengeluaran menerima kategori | Kategori dapat dimuat dan pengeluaran baru tersimpan serta muncul kembali setelah refresh | P0 |
| API satuan dan inventori | Sediakan data satuan bahan baku dan lengkapi alur bahan baku, pembelian, pergerakan stok, dan stok opname | Admin dapat menyimpan bahan dengan satuan, mencatat pembelian dan opname, dan melihat hasilnya konsisten pada katalog/stok | P0 |
| CRUD manajemen | Lengkapi operasi yang dibutuhkan untuk menu, kategori, modifier, channel, resep, meja/QR, pengguna, perangkat, serta pengaturan yang ditampilkan aplikasi | Perubahan tersimpan di server, mengikuti RBAC, dan dapat dimuat ulang tanpa mengandalkan data lokal sementara | P0 |
| Ketahanan operasional | Lengkapi batas sesi offline 7 hari, penanganan void/refund sesuai izin, dan validasi alur sync serta laporan offline | Sesi kedaluwarsa ditolak sesuai aturan; koreksi transaksi tercatat; perilaku online/offline lulus skenario uji | P0 |
| Operasi rilis | UAT di outlet, uji perangkat/printer, uji keamanan dan beban, monitoring error, backup dan uji restore | Pemilik produk menyetujui UAT; tidak ada defect kritis terbuka; prosedur pemulihan dan dukungan operasional tersedia | P0 |

### 13.2 Gap implementasi yang diketahui

Gap berikut dicatat dari integrasi frontend dan backend yang tersedia saat ini. Periksa ulang kontrak endpoint dan implementasi backend sebelum menganggap suatu item selesai.

- QRIS di web saat ini belum terhubung ke payment gateway sungguhan; kredensial merchant, verifikasi webhook produksi, rekonsiliasi, dan refund harus disiapkan.
- Pengiriman push notification dan pengelolaan token perangkat belum siap; WebSocket hanya mencakup pembaruan realtime saat aplikasi aktif.
- Android memiliki retry terjadwal, sedangkan iOS belum memiliki jaminan sync berkala di background. Sync saat foreground/reconnect tetap wajib.
- API kategori pengeluaran dan satuan bahan baku belum tersedia. Akibatnya pembuatan pengeluaran, bahan baku yang memerlukan satuan, pembelian, dan opname belum dapat diselesaikan end-to-end.
- Sebagian operasi CRUD manajemen, pengaturan, void/refund, laporan offline, dan penegakan masa sesi offline 7 hari masih perlu dilengkapi atau diverifikasi.

## 14. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| QR menu butuh internet, outlet offline tidak bisa menerima pesanan QR | Pelanggan tidak bisa memesan | Tampilkan pesan arahan ke kasir. Fase lanjut: mode LAN lokal atau router cadangan 4G |
| Stok minus karena sync tertunda | Saldo stok sementara keliru | Ledger movement, flag audit, rekonsiliasi lewat opname |
| Printer Bluetooth beragam merek | Struk gagal cetak | Uji 2–3 merek umum, siapkan fallback bagikan PDF |
| Notifikasi tertunda karena battery optimization | Pesanan QR terlambat dilihat | WebSocket saat app aktif, FCM prioritas tinggi, alarm berulang, panduan pengaturan HP kasir |
| Jam perangkat salah | Laporan per tanggal keliru | Pakai waktu server saat sync dan tandai selisih |
| WebSocket di Flask kurang stabil di skala besar | Notifikasi terputus | Flask-SocketIO dengan gevent dan Redis message queue |
| Migrasi skema SQLite saat update app | App crash setelah update | Migrasi Drift berversi dan tes upgrade tiap rilis |
| Integrasi API GoFood dkk. butuh kemitraan | Tidak otomatis | Input manual dulu, integrasi di fase lanjut |
| Webhook gateway telat atau gagal | Pelanggan sudah bayar tetapi pesanan belum masuk | Server mengecek ulang status tagihan lewat API gateway secara berkala sebelum menandai EXPIRED |
| Akun kasir dipakai di banyak perangkat | HP yang hilang bisa disalahgunakan, dan sulit mengetahui perangkat mana yang melakukan transaksi | Perangkat harus terdaftar dengan batas jumlah aktif, Admin bisa mencabut perangkat kapan saja, setiap transaksi mencatat device_id, ganti password atau PIN bila HP hilang |
| Konfirmasi QRIS statis di kasir dilakukan manual | Kasir bisa salah menandai lunas, atau pelanggan mengaku sudah bayar padahal uang belum masuk | Kasir wajib mengecek notifikasi uang masuk sebelum menandai lunas, dan setiap konfirmasi QRIS tercatat di audit log |

## 15. Keputusan dan Pertanyaan Terbuka

**Sudah diputuskan:**

- Fokus 1 outlet. Gambaran multi-outlet hanya referensi di Lampiran A.
- Tidak ada PPN dan service charge.
- Pembayaran: tunai dan QRIS. Di kasir memakai QRIS statis (dikonfirmasi manual oleh kasir, tetap jalan offline). Di QR menu memakai QRIS dinamis lewat payment gateway.
- Kasir hanya 1 akun yang bisa dipakai di beberapa perangkat (jumlah perangkat aktif dibatasi dan bisa diatur), dan boleh melihat semua data laporan, pengeluaran, kas, dan grafik untuk semua tanggal.
- QR menu bersifat opsional: pelanggan boleh memesan lewat QR atau langsung ke kasir.
- Pesanan QR dengan QRIS otomatis diterima setelah lunas. Pesanan QR tunai disetujui kasir dulu, lalu kasir menyerahkan nota langsung ke pelanggan.
- Delivery hanya lewat platform (GoFood dkk.), tanpa kurir sendiri dan ongkir. Delivery tidak tersedia di QR menu.
- QR menu berupa web ringan.
- Diskon manual saja. Member dan voucher belum ada konsep dari klien, jadi di luar lingkup.

**Masih terbuka** (asumsi di dokumen ini tetap dipakai sampai dijawab):

- Merek dan tipe printer thermal belum dipilih. Syarat yang disarankan: Bluetooth, mendukung ESC/POS, lebar kertas 58 mm atau 80 mm.
- Apakah perlu versi iOS? Dokumen ini mengasumsikan Android dulu.
- Apakah HPP dan laba juga boleh dilihat kasir? Dokumen ini mengasumsikan tidak.
- Payment gateway mana yang dipilih untuk QRIS dinamis, dan apakah dokumen usaha untuk mendaftar merchant sudah siap?

## 16. Langkah Selanjutnya

- Jawab pertanyaan terbuka yang tersisa di bagian 15.
- Finalisasi ERD dan skema SQLite/MySQL.
- Wireframe layar Kasir, Inbox QR, dan Inventori.
- Spesifikasi OpenAPI untuk Flask.
- Skeleton proyek Flutter (struktur folder, Drift, sync worker) dan proyek Flask (blueprint, Alembic, JWT).

## Lampiran A. Gambaran Versi Multi-Outlet (Hanya Referensi)

Lampiran ini hanya gambaran arah jika Jou Coffee membuka cabang. Tidak masuk roadmap dan tidak dikerjakan di versi 1 outlet.

| Area | Versi 1 outlet (dokumen utama) | Jika multi-outlet |
| --- | --- | --- |
| Database | Tanpa tabel outlets dan kolom outlet_id | Tambah tabel outlets dan kolom outlet_id di semua tabel transaksi, stok, kas, dan perangkat. Data lama diisi dengan satu outlet awal |
| Role | Tiga role, akses ke seluruh data | Tetap tiga role. Kasir dan Admin/Owner terikat ke outlet tertentu, Super Admin melihat semua outlet |
| Menu dan harga | Satu katalog | Katalog global dengan opsi harga dan ketersediaan per outlet |
| Stok dan resep | Satu stok | Stok per outlet, resep global, ditambah fitur transfer stok antar outlet |
| Laporan | Satu laporan | Laporan per outlet, dan gabungan semua outlet untuk Super Admin |
| Sinkronisasi | Satu cursor sync | Pull difilter per outlet, cursor per outlet dan perangkat |
| Nomor struk | Kode perangkat, tanggal, urut | Kode outlet ditambahkan di awal nomor |
| QR menu | Satu set QR meja | Token meja dan notifikasi dipisah per outlet |
| Pajak dan service charge | Tidak ada | Bisa diatur per outlet bila dibutuhkan |

Menambah outlet_id belakangan butuh migrasi di server dan di SQLite semua perangkat. Perkiraan kasar tambahan pekerjaannya 3–4 sprint, terutama untuk migrasi data dan pengujian sinkronisasi.

## Lampiran B. Pembayaran QRIS Dinamis di QR Menu dan Keamanannya

Pembayaran QRIS di QR menu aman bila uangnya diproses payment gateway berizin, bukan oleh aplikasi sendiri, dan status lunas hanya dipercaya dari notifikasi server gateway. QRIS di QR menu harus QRIS dinamis lewat gateway, karena QRIS statis tidak bisa memberi tahu sistem secara otomatis bahwa pelanggan sudah bayar. Fitur ini bagian dari QR menu dan membuat pesanan QRIS otomatis diterima setelah lunas, tanpa approval kasir. Di kasir (POS), QRIS tetap memakai QRIS statis yang dikonfirmasi manual.

### Alur pembayaran QRIS

- Pelanggan memilih menu, lalu memilih QRIS di checkout.
- Server memeriksa ketersediaan menu, menghitung total sendiri, lalu membuat tagihan QRIS dinamis lewat API gateway dengan batas waktu bayar (status AWAITING_PAYMENT).
- Pelanggan membayar lewat e-wallet atau m-banking.
- Gateway memanggil webhook ke server. Server memverifikasi tanda tangan, mencocokkan ID tagihan dan nominal, lalu menandai pesanan PAID dan APPROVED sekaligus.
- Pesanan masuk laporan, stok dipotong, dan perangkat kasir menerima notifikasi. Kasir mencetak nota dan tiket dapur.
- Tagihan yang tidak dibayar sampai batas waktu menjadi EXPIRED tanpa memengaruhi laporan dan stok.

### Risiko keamanan dan pengamanannya

| Risiko | Pengamanan |
| --- | --- |
| Pelanggan memalsukan status lunas atau nominal | Total dihitung di server. Status PAID hanya berubah dari webhook gateway yang terverifikasi, tidak pernah dari browser pelanggan |
| Webhook palsu | Verifikasi tanda tangan atau secret dari gateway, lalu cek ulang status tagihan lewat API gateway sebelum menandai PAID |
| Webhook terkirim dobel | Handler idempoten berdasarkan ID transaksi gateway, PAID tidak diproses dua kali |
| Data kartu atau e-wallet bocor | Pembayaran terjadi di aplikasi e-wallet atau halaman gateway. Sistem tidak pernah menyimpan data kartu atau PIN |
| Pesanan spam atau iseng | Token meja bertanda tangan, rate limit, tagihan kedaluwarsa otomatis |
| Uang masuk tetapi pesanan batal | Refund lewat gateway, dicatat sebagai REFUNDED di payments dengan PIN Admin |
| Catatan tidak cocok dengan uang masuk | Rekonsiliasi harian antara laporan gateway dan tabel payments, selisih ditandai |
| API key bocor | Key dan secret hanya di server (environment variable), tidak ada di aplikasi Flutter atau web QR, dirotasi berkala |
| Lalu lintas disadap | HTTPS wajib di semua endpoint |
| Gateway atau internet bermasalah | Pelanggan tetap bisa memilih Tunai dan membayar ke kasir |
| Pesanan QRIS lunas tetapi bahan ternyata habis | Server memeriksa stok sebelum tagihan dibuat, menu yang habis otomatis tidak bisa dipesan, dan bila tetap gagal pesanan direfund lewat gateway |

**Perubahan teknis:** tabel payments ditambah kolom provider, provider_ref, paid_at, dan raw_webhook. Endpoint publik baru POST /public/payments/webhook, tanpa JWT dan hanya dipercaya setelah tanda tangan terverifikasi.

**Cek ke penyedia sebelum mulai:** biaya per transaksi, lama pencairan ke rekening, dokumen pendaftaran merchant, dan ketersediaan QRIS dinamis. Contoh penyedia di Indonesia: Midtrans, Xendit, dan DOKU.