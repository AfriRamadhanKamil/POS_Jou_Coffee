# 📋 Master Development Plan — POS Jou Coffee

> Dokumen perencanaan implementasi menyeluruh (End-to-End) sistem POS Jou Coffee berdasarkan **PRD Versi 2.0**.
> **Target Pengguna Dokumen:** Programmer Junior / Model AI untuk implementasi mandiri per fase.
> **Karakter Dokumen:** **High-Level** (fokus pada arsitektur, apa yang dibangun, batasan aturan bisnis, dan tolok ukur selesai; tanpa potongan kode sintaksis).

---

## 1. Ringkasan Sistem & Arsitektur

Jou Coffee POS adalah sistem kasir terpadu untuk **satu outlet** kopi yang mengusung prinsip **offline-first**: kasir tetap bisa melayani transaksi secara cepat tanpa koneksi internet, dan seluruh data otomatis tersinkronisasi ke server pusat saat online.

### Komponen Arsitektur:
- **Aplikasi Kasir (Mobile):** Aplikasi kasir berbasis Flutter untuk perangkat Android (HP dan Tablet, mendukung orientasi Portrait dan Landscape).
- **Database Lokal:** SQLite di perangkat kasir untuk memastikan seluruh operasi transaksi tersimpan lokal tanpa jeda loading server.
- **Backend Service:** REST API berbasis Flask dengan database server MySQL 8.
- **Realtime & Notifikasi:** WebSocket untuk komunikasi instan antar-perangkat kasir saat aplikasi aktif, dan FCM (Firebase Cloud Messaging) untuk notifikasi background.
- **QR Menu Pelanggan:** Halaman web mandiri (PWA ringan) tanpa login dan tanpa instalasi aplikasi untuk pemesanan langsung dari meja.
- **Payment Gateway:** Integrasi pihak ketiga untuk penerbitan tagihan QRIS dinamis dan notifikasi pelunasan otomatis via webhook.

---

## 2. Aturan Mutlak (Guardrails yang Wajib Dipatuhi)

1. **Offline-First:** Semua aksi kasir (katalog, transaksi, bayar, shift kas) wajib masuk ke database lokal terlebih dahulu. Layar tidak boleh menunggu respons jaringan server.
2. **ID dari Perangkat (UUID):** Semua ID data dibuat di aplikasi menggunakan format UUID agar tidak terjadi bentrok data saat sinkronisasi multi-perangkat.
3. **Nomor Struk Standar:** Format nomor struk: `JOU-{KODE_DEVICE}-{YYYYMMDD}-{NOMOR_URUT}` (Contoh: `JOU-K01-20261116-0001`).
4. **Sinkronisasi Idempoten:** Pengiriman ulang batch data yang sama tidak boleh menimbulkan duplikasi data di database server.
5. **Data Transaksi Append-Only:** Transaksi tidak pernah dihapus fisik. Pembatalan/koreksi dilakukan melalui transaksi void/refund baru. Master data menggunakan soft delete.
6. **Resolusi Konflik:** Master data: server menang. Jika dua perangkat memproses pesanan yang sama: pesanan yang pertama tiba di server menang, perangkat lain menerima pemberitahuan pembaruan.
7. **Stok Berbasis Ledger:** Perubahan stok dicatat sebagai riwayat pergerakan (masuk/keluar), bukan menimpa angka saldo secara langsung. Stok diperbolehkan minus sementara jika terjadi penjualan offline paralel, dan ditandai untuk diaudit.
8. **Validasi Hak Akses di Server:** Validasi role (RBAC) ditegakkan di backend melalui klaim token JWT. Menyembunyikan tombol di aplikasi saja tidak cukup. Saat offline, hak akses divalidasi dari cache lokal.
9. **Presisi Keuangan & Format Waktu:** Nilai uang menggunakan format desimal presisi (bukan float) dalam Rupiah. Waktu internal disimpan dalam UTC dan ditampilkan dalam zona waktu WIB. Harga menu adalah harga final: **tanpa PPN dan tanpa service charge**.
10. **Aksi Sensitif Butuh PIN Admin:** Tindakan sensitif (Void transaksi, Refund, Diskon khusus di atas batas) wajib meminta konfirmasi PIN Admin/Owner dan tercatat di audit log.
11. **UX Kasir:** Antarmuka kasir menggunakan bahasa Indonesia, tombol berukuran besar, dan konfirmasi jelas untuk aksi kritis.

---

## 3. Peran Pengguna & Hak Akses (RBAC)

Sistem hanya memiliki **tiga role**:
- **Kasir:** Operasional penjualan POS, approval pesanan QR, buka/tutup shift, kas masuk/keluar, tambah pengeluaran, dan melihat laporan penjualan (Kasir **dilarang melihat HPP dan laba kotor**). Hanya ada **1 akun Kasir** yang dapat digunakan di beberapa perangkat aktif sekaligus (maksimal perangkat dibatasi).
- **Admin / Owner:** Seluruh akses kasir ditambah manajemen katalog menu, bahan baku, resep BOM, penyesuaian stok, manajemen meja/QR, kelola akun kasir, dan laporan laba lengkap.
- **Super Admin:** Pengelola teknis sistem. Seluruh akses Admin ditambah kelola akun Admin, pengaturan sistem outlet, audit log, dan pencabutan hak perangkat.

---

## 4. Rincian Perencanaan per Fase (Roadmap Implementasi)

Pengerjaan wajib dilakukan secara berurutan. Jangan memulai fase berikutnya sebelum kriteria **"Selesai Bila"** pada fase aktif terpenuhi secara utuh.

---

### Issue #0: Fondasi Sistem & Kerangka Proyek (Fase 0)

**Tujuan:** Menyiapkan struktur dasar aplikasi mobile dan backend API agar pengembangan fitur selanjutnya berjalan mulus tanpa pembongkaran arsitektur.

**Cakupan Pekerjaan:**
- **Backend:** Setup kerangka proyek modular berbasis blueprint, konfigurasi database MySQL, migrasi database berversi, dan standarisasi respons error JSON.
- **Mobile Kasir:** Setup kerangka aplikasi Flutter, state management, routing deklaratif, dan skema database relasional lokal (SQLite).
- **Desain UI Responsif:** Skema layout adaptif untuk HP Android (portrait) dan Tablet Android (landscape dua panel: katalog di kiri, keranjang transaksi di kanan).
- **Protokol API:** Menetapkan format standar endpoint dengan prefiks `/api/v1` dan autentikasi token.

**Selesai Bila:**
- Kerangka backend API berhasil dijalankan dan merespons health-check.
- Kerangka aplikasi mobile berhasil dibuild ke perangkat HP dan tablet Android, serta database lokal terinisialisasi dengan benar.

---

### Issue #1: Autentikasi, Hak Akses Role & Manajemen Perangkat (Fase 1)

**Tujuan:** Memastikan setiap pengguna masuk dengan hak akses yang tepat dan perangkat yang terdaftar resmi.

**Cakupan Pekerjaan:**
- **Login Pengguna:** Login menggunakan username & password. Kasir disediakan opsi login cepat dengan PIN 6 digit.
- **Token Akses:** Penerbitan access token berumur pendek (15 menit) dan refresh token untuk perpanjangan sesi.
- **Registrasi Perangkat:** Perangkat kasir mencatatkan identitas unik (`device_id`) saat login pertama kali. Jumlah perangkat aktif dibatasi (default 3 perangkat). Admin/Super Admin dapat mencabut akses perangkat yang hilang atau rusak.
- **Sesi Offline:** Kredensial dan hak akses role disimpan terenkripsi di perangkat untuk validasi login saat tidak ada internet. Batasi durasi sesi offline maksimal 7 hari; lewat dari batas tersebut wajib terhubung ke internet.
- **Navigasi Dinamis:** Tampilan menu di aplikasi otomatis menyembunyikan modul yang tidak sesuai dengan role akun.
- **Audit Log (P1):** Pencatatan riwayat aksi sensitif pengguna.

**Selesai Bila:**
- Akun kasir dan admin login dengan benar sesuai kredensialnya.
- Saat koneksi internet dimatikan, login tetap berfungsi normal melalui cache lokal.
- Menu khusus Admin tidak dapat diakses oleh Kasir.
- Perangkat yang dicabut izinnya oleh Admin otomatis ditolak saat login maupun sinkronisasi.

---

### Issue #2: Master Menu & Katalog Penjualan (Fase 2)

**Tujuan:** Admin dapat mengelola menu yang akan dijual, dan katalog menu tersedia untuk operasional kasir.

**Cakupan Pekerjaan:**
- **Katalog Menu:** Pengelolaan kategori menu, item menu, foto, harga dasar, dan status ketersediaan.
- **Varian & Modifier:** Penambahan opsi ukuran, tingkat es, gula, dan topping dengan penambahan harga masing-masing.
- **Channel Penjualan:** Konfigurasi channel penjualan (GoFood, GrabFood, ShopeeFood) beserta harga khusus per channel dan persentase komisi platform. Opsi penambahan channel baru (P1).
- **Katalog POS:** Penyediaan data katalog siap saji yang efisien untuk dibaca layar kasir.

**Selesai Bila:**
- Admin dapat menambah, mengubah, dan menonaktifkan menu beserta varian/modifier-nya.
- Seluruh katalog menu tersimpan di server dan terbaca sempurna oleh akun Kasir.

---

### Issue #3: Mesin Sinkronisasi Dua Arah & Indikator Status (Fase 3)

**Tujuan:** Membangun mekanisme pertukaran data otomatis antara database lokal kasir dan server cloud tanpa mengganggu responsivitas antarmuka.

**Cakupan Pekerjaan:**
- **Antrean Lokal (Sync Outbox):** Setiap aksi kasir saat online maupun offline otomatis dicatat ke antrean perubahan lokal.
- **Sinkronisasi Push (Upload):** Pengiriman batch data transaksi dari antrean lokal ke server cloud dengan validasi kunci idempotensi untuk mencegah duplikasi.
- **Sinkronisasi Pull (Download):** Pengambilan pembaruan master data dari server menggunakan penanda versi server terkini (`server_version`).
- **Pemicu Sinkronisasi:** Otomatis saat aplikasi dibuka, saat koneksi internet kembali pulih, sesaat setelah transaksi selesai, secara berkala di latar belakang, dan tombol manual.
- **Indikator Status UI:** Menampilkan status jaringan secara transparan di layar kasir (Online, Offline, Sedang Menyinkronkan, atau Jumlah Data Menunggu Sync).
- **Deteksi Selisih Waktu:** Server menandai data jika selisih waktu perangkat kasir lebih dari 5 menit terhadap waktu server.
- **Retensi Data Lokal:** Perangkat hanya menyimpan riwayat transaksi 90 hari terakhir untuk menghemat penyimpanan; data historis lengkap tetap tersimpan di server.

**Selesai Bila:**
- Data master menu otomatis terunduh ke perangkat baru dan tetap dapat dibuka saat internet diputus.
- Transaksi yang dilakukan berulang kali saat offline terunggah utuh ke server begitu internet aktif tanpa ada duplikasi atau data hilang.
- Indikator jaringan di antarmuka kasir mencerminkan status riil secara tepat.

---

### Issue #4: Layar POS Kasir, Transaksi Offline & Cetak Struk (Fase 4)

**Tujuan:** Kasir dapat menjalankan transaksi penjualan secara cepat, akurat, dan mencetak bukti pembayaran dalam kondisi online maupun offline.

**Cakupan Pekerjaan:**
- **Antarmuka POS:** Katalog menu per kategori, pencarian cepat, pemilihan varian dan modifier, serta tanda "Habis" jika stok tidak tersedia.
- **Tipe Pesanan:** Pilihan Dine In (input/pilih nomor meja) dan Take Away.
- **Keranjang Pesanan:** Ubah jumlah pesanan, catatan khusus per item, serta diskon manual (nominal/persen) per item atau total nota. Diskon di atas batas yang ditentukan wajib meminta otorisasi PIN Admin.
- **Metode Pembayaran:**
  - *Tunai:* Kalkulasi uang diterima, tombol preset pecahan uang cepat, dan perhitungan uang kembalian.
  - *QRIS Statis:* Tampilan kode QRIS statis outlet di layar kasir; kasir melakukan verifikasi dana masuk secara manual (dapat digunakan saat offline, tercatat di audit log).
- **Simpan Pesanan (P1):** Fitur menahan (hold) pesanan yang belum dibayar untuk melayani antrean lain terlebih dahulu.
- **Cetak Struk Thermal:** Integrasi printer Bluetooth thermal ESC/POS (ukuran kertas 58 mm dan 80 mm) untuk mencetak struk kasir, tiket dapur/bar, dan cetak ulang struk. Siapkan opsi bagikan struk digital (PDF/gambar) sebagai cadangan.
- **Koreksi Transaksi (Void/Refund) (P1):** Pembatalan pesanan yang sudah selesai wajib meminta PIN Admin, dicatat sebagai transaksi pembalik, dan mengembalikan stok.
- **Status Transaksi:** Pesanan POS langsung berstatus selesai/disetujui (APPROVED).

**Selesai Bila:**
- Transaksi dari pemilihan menu hingga selesai bayar tersimpan lokal dalam waktu < 1 detik saat offline.
- Struk berhasil tercetak dengan tata letak rapi pada printer thermal Bluetooth 58 mm dan 80 mm.
- Seluruh transaksi offline terunggah ke server tanpa selisih saat online kembali.

---

### Issue #5: Manajemen Kas Laci, Shift & Pengeluaran Operasional (Fase 5)

**Tujuan:** Mengontrol arus kas fisik di laci kasir secara disiplin dan mencatat biaya pengeluaran harian outlet.

**Cakupan Pekerjaan:**
- **Buka Shift:** Kasir wajib menginput modal awal kas laci sebelum dapat melakukan transaksi penjualan.
- **Kas Masuk & Keluar:** Pencatatan uang tunai non-penjualan (misalnya: penambahan uang receh kembalian atau penarikan kas untuk disetor).
- **Tutup Shift:** Perhitungan otomatis saldo kas yang seharusnya ada di laci (Modal Awal + Penjualan Tunai + Kas Masuk − Kas Keluar − Pengeluaran Tunai). Kasir menginput kas fisik aktual, dan sistem menghitung selisih kas. Fitur cetak ringkasan shift ke printer struk.
- **Rekonsiliasi Admin:** Admin dapat meninjau dan merekonsiliasi seluruh riwayat shift kasir.
- **Pengeluaran Operasional:** Kasir dapat mencatat pengeluaran operasional (kategori biaya, nominal, catatan keterangan, dan foto bukti nota). Admin memiliki hak penuh mengelola pengeluaran.
- **Kepatuhan Offline:** Seluruh alur shift dan pengeluaran berfungsi penuh saat offline dan tersinkronisasi otomatis saat online.

**Selesai Bila:**
- Shift dapat dibuka dan ditutup dalam kondisi offline dengan perhitungan selisih kas yang akurat.
- Pembayaran non-tunai (QRIS & Platform) tidak tercampur ke dalam saldo kas fisik laci kasir.
- Pengeluaran yang diinput saat offline tersimpan lokal dan terunggah ke server tanpa kendala.

---

### Issue #6: Pesanan Online Platform, Laporan & Grafik Penjualan (Fase 6)

**Tujuan:** Mengintegrasikan pencatatan pesanan dari platform delivery (GoFood, GrabFood, ShopeeFood) ke dalam satu laporan penjualan terpadu.

**Cakupan Pekerjaan:**
- **Mode Pesanan Online (Delivery Manual):** Kasir memilih channel pengiriman, memasukkan ID pesanan eksternal dari aplikasi merchant, dan memilih menu dengan harga otomatis sesuai channel.
- **Perhitungan Bersih:** Sistem mencatat omzet kotor, persentase potongan komisi platform, dan omzet bersih yang diterima outlet. Pembayaran metode "Platform" tidak dimasukkan ke laci kas tunai.
- **Pelacakan Status Pesanan Online (P1):** Status tahapan pesanan (Diterima, Diproses, Siap, Diambil Driver).
- **Laporan Penjualan:** Rekapitulasi penjualan harian, mingguan, dan bulanan dengan filter berdasarkan tipe pesanan, channel penjualan, metode bayar, dan nama kasir.
- **Laporan Laba Kotor (P1):** Menampilkan perolehan pendapatan dikurangi HPP (harga pokok penjualan dari resep). Modul ini **hanya dapat diakses oleh Admin/Owner dan Super Admin**.
- **Grafik Penjualan:** Visualisasi grafik tren penjualan per jam dan per hari, menu terlaris, persentase channel, dan metode pembayaran.
- **Ekspor & Mode Offline (P1):** Laporan penjualan dapat dilihat saat offline dari basis data lokal, serta dapat diekspor ke format PDF dan Excel.

**Selesai Bila:**
- Pesanan platform eksternal tercatat rapi dengan perhitungan komisi yang tepat.
- Angka pada laporan penjualan mencocokkan seluruh transaksi POS dan pesanan online secara akurat.
- Akun dengan role Kasir terbukti tidak dapat melihat rincian HPP maupun laba kotor.

---

### Issue #7: Inventori: Bahan Baku, Resep & Manajemen Stok (Fase 7)

**Tujuan:** Mengontrol ketersediaan bahan baku, memotong stok secara otomatis berdasarkan resep setiap kali menu terjual, dan melacak selisih stok.

**Cakupan Pekerjaan:**
- **Master Bahan Baku:** Manajemen satuan ukur dan bahan mentah (satuan, ambang batas stok minimal, dan harga beli terakhir). Modul ini tersembunyi dari akun Kasir.
- **Resep Produk (BOM):** Pemetaan setiap menu dan variannya ke daftar bahan baku beserta takaran kuantitasnya. Sistem menghitung estimasi HPP produk secara otomatis.
- **Pencatatan Stok:** Pencatatan stok masuk dari pembelian bahan, penyesuaian stok, pencatatan bahan rusak/terbuang (waste), dan pencatatan stok opname berkala.
- **Pemotongan Stok Otomatis:** Setiap transaksi penjualan yang disetujui (APPROVED) otomatis memotong stok bahan terkait sesuai komposisi resep. Jika transaksi di-void, stok otomatis dikembalikan melalui pencatatan pembalik.
- **Indikator Habis di Layar Kasir:** Jika saldo stok bahan habis di sistem, menu terkait otomatis menampilkan label "Habis" di layar POS dan dapat dinonaktifkan (P1).
- **Notifikasi Stok Menipis (P1):** Peringatan otomatis jika stok bahan berada di bawah batas minimum.

**Selesai Bila:**
- Transaksi menu berhasil mengurangi stok bahan baku sesuai takaran resep yang ditentukan.
- Dua perangkat yang melakukan transaksi penjualan offline secara bersamaan tidak saling menimpa saldo stok saat sinkronisasi (menggunakan model pergerakan ledger).
- Stok opname menghasilkan pencatatan selisih dan penyesuaian saldo yang terdokumentasi rapi.

---

### Issue #8: QR Menu Pemesanan Mandiri, Notifikasi & Approval Kasir (Fase 8)

**Tujuan:** Pelanggan dapat memesan menu langsung dari meja menggunakan ponselnya sendiri, dan pesanan tunai masuk ke antrean kasir untuk disetujui.

**Cakupan Pekerjaan:**
- **Manajemen Meja & QR:** Admin mengelola daftar nomor meja dan mencetak kode QR meja unik dengan token bertanda tangan yang dapat diperbarui (regenerate).
- **Web QR Menu (PWA Publik):** Pelanggan memindai QR, melihat katalog menu aktif tanpa harus login atau menginstal aplikasi. Pelanggan memilih tipe pesanan Dine In (meja otomatis terisi) atau Take Away (input nama pemanggil).
- **Pesanan Tunai Pelanggan:** Pesanan tunai masuk dengan status menunggu persetujuan kasir (`PENDING_APPROVAL`).
- **Notifikasi Kasir:** Seluruh perangkat kasir yang aktif menerima notifikasi realtime (suara audio, push notification, dan indikator badge angka pesanan masuk).
- **Aksi Approval Kasir:** Kasir dapat menyetujui pesanan (**Terima**), menolak (**Tolak** dengan alasan wajib), atau menyesuaikan item terlebih dahulu (**Edit**).
- **Pemrosesan Pesanan:** Begitu disetujui kasir, status berubah menjadi `APPROVED`, stok bahan otomatis terpotong, pesanan masuk ke laporan, serta kasir mencetak nota pelanggan dan tiket dapur.
- **Halaman Status Pelanggan:** Pelanggan dapat memantau status pesanannya di layar HP sendiri (Menunggu Konfirmasi, Diterima, Diproses, Siap Diambil/Disajikan) dengan nomor antrean.
- **Proteksi & Kedaluwarsa:** Pembatasan frekuensi pesanan (rate limit) untuk mencegah spam. Pesanan tunai yang tidak direspons kasir lebih dari batas waktu (default 10 menit) otomatis menjadi kedaluwarsa (`EXPIRED`) (P1).

**Selesai Bila:**
- Pesanan tunai dari web pelanggan muncul di seluruh perangkat kasir aktif dalam hitungan detik.
- Kasir dapat menyetujui pesanan, memotong stok, mencetak tiket dapur, dan mengabari pelanggan hingga pesanan selesai disajikan.
- Gangguan jaringan tidak menghilangkan data antrean pesanan pada kasir.

---

### Issue #9: Pembayaran QRIS Dinamis via Payment Gateway (Fase 9)

**Tujuan:** Pelanggan dapat membayar pesanan QR menu menggunakan QRIS dinamis dari HP-nya dan pesanan otomatis disetujui tanpa perlu approval manual kasir.

**Prasyarat:** Payment gateway telah ditentukan dan akun merchant telah aktif.

**Cakupan Pekerjaan:**
- **Penerbitan QRIS Dinamis:** Pelanggan memilih metode bayar QRIS saat checkout di web menu. Server memvalidasi ketersediaan stok, menghitung total, dan membuat tagihan QRIS dinamis melalui payment gateway dengan batas waktu bayar (status `AWAITING_PAYMENT`).
- **Webhook Verifikasi Pembayaran:** Endpoint webhook publik menerima notifikasi pelunasan dari payment gateway, memverifikasi tanda tangan keamanan, mencocokkan nominal, dan memproses status secara idempoten.
- **Persetujuan Otomatis:** Setelah pembayaran terverifikasi lunas, status pesanan otomatis berubah menjadi lunas (`PAID`) dan disetujui (`APPROVED`) secara bersamaan.
- **Notifikasi Kasir & Auto-Print:** Perangkat kasir menerima pemberitahuan pesanan QRIS telah lunas, stok terpotong, dan kasir langsung mencetak nota transaksi serta tiket dapur.
- **Kedaluwarsa Tagihan:** Tagihan QRIS yang tidak dibayar hingga batas waktu otomatis menjadi `EXPIRED` tanpa memengaruhi stok maupun laporan keuangan.
- **Batal & Refund QRIS (P1):** Jika pesanan QRIS yang sudah dibayar dibatalkan (misal: stok fisik mendadak tidak mencukupi), pengembalian dana (refund) diproses melalui payment gateway dengan persetujuan PIN Admin.

**Selesai Bila:**
- Pengujian pembayaran QRIS dinamis berhasil end-to-end (tagihan terbit, dibayar, webhook tervalidasi, pesanan otomatis approved, dan stok terpotong).
- Webhook palsu ditolak server, dan notifikasi webhook yang terkirim ganda tidak memproses pesanan dua kali.

---

### Issue #10: Pengujian Perangkat Fisik, Migrasi Skema & Kesiapan Rilis (Fase 10)

**Tujuan:** Memastikan seluruh sistem berjalan stabil, bebas error kritis, dan siap beroperasi di outlet fisik.

**Cakupan Pekerjaan:**
- **Uji Perangkat Nyata:** Pengujian menyeluruh pada HP Android dan Tablet Android fisik (Android versi 7.0 ke atas), baik mode portrait maupun landscape.
- **Optimasi Daya & Notifikasi:** Pengujian notifikasi suara dan push pada berbagai merek perangkat kasir dengan mengonfigurasi pengecualian penghemat daya baterai (battery optimization).
- **Uji Kompatibilitas Printer:** Pengujian stabilitas cetak struk dan tiket pesanan pada beberapa merek printer Bluetooth thermal standar.
- **Uji Skenario Ekstrem:** Pengujian simulasi penjualan massal saat jaringan internet diputus tiba-tiba, pengujian batas sesi offline 7 hari, dan pengujian rekonsiliasi data saat koneksi pulih.
- **Uji Migrasi Basis Data:** Memastikan peningkatan versi aplikasi di masa mendatang tidak merusak atau menghapus data lokal kasir yang belum sempat tersinkronisasi.
- **Monitoring & Cadangan:** Pemasangan alat pemantau crash/error aplikasi, pencatatan log sinkronisasi server, dan pengujian pemulihan data cadangan database server secara berkala.
- **Uji Penerimaan Pengguna (UAT):** Simulasi operasional harian outlet bersama pemilik produk hingga dinyatakan siap rilis.

**Selesai Bila:**
- Seluruh fitur prioritas P0 berfungsi sempurna tanpa cacat kritis terbuka.
- Aplikasi terbukti andal dalam pergantian mode offline-online di perangkat fisik nyata.
- Prosedur operasional dan pencadangan data siap digunakan di lingkungan produksi.

---

## 5. Ringkasan Ketergantungan Fase (Roadmap)

```
[Fondasi & Akses]
  Fase 0 (Fondasi) 
    └── Fase 1 (Autentikasi, Role, Perangkat)
          └── Fase 2 (Master Menu / Katalog)
                └── Fase 3 (Mesin Sinkronisasi Offline-Online)

[Operasional Kasir]
  Fase 3 
    └── Fase 4 (POS Kasir & Cetak Struk)
          ├── Fase 5 (Kas, Shift & Pengeluaran)
          ├── Fase 6 (Pesanan Online Platform & Laporan)
          └── Fase 7 (Inventori Bahan Baku, Resep & Stok)

[Integrasi Pemesanan Mandiri Pelanggan]
  Fase 4 + Fase 7 
    └── Fase 8 (QR Menu Tunai & Notifikasi Kasir)
          └── Fase 9 (Pembayaran QRIS Dinamis via Gateway)

[Peluncuran]
  Semua Fase (0 s/d 9) 
    └── Fase 10 (Pengujian Perangkat Nyata, Hardening & Rilis)
```

---

## 6. Checklist Verifikasi Implementasi (Bagi Developer / AI)

Sebelum menyatakan suatu tugas selesai, lakukan pemeriksaan mandiri berikut:
- [ ] Apakah fitur tetap berjalan lancar saat mode pesawat diaktifkan (tanpa internet)? *(Kecuali modul web QR pelanggan dan webhook gateway yang memang butuh jaringan).*
- [ ] Apakah seluruh pembuatan data baru menggunakan ID berformat UUID dari perangkat?
- [ ] Apakah tampilan antarmuka kasir sudah diuji pada resolusi HP (Portrait) dan Tablet (Landscape)?
- [ ] Apakah kasir berhasil dicegah dari melihat angka HPP dan margin laba kotor?
- [ ] Apakah aksi sensitif (void, refund, diskon khusus) selalu meminta verifikasi PIN Admin?
- [ ] Apakah nilai mata uang dihitung tanpa pembulatan pecahan desimal yang keliru?
- [ ] Apakah data transaksi yang dibuat saat offline langsung tercatat di antrean sinkronisasi lokal?
