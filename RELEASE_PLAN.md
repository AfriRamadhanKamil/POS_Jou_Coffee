# Rencana Lanjutan hingga Rilis Aman — POS Jou Coffee

Dokumen ini menjadi urutan kerja dan checklist dari kondisi implementasi saat ini sampai rilis produksi. PRD versi 1.4 tetap menjadi sumber kebutuhan produk. Jangan melewati gerbang rilis hanya karena aplikasi berhasil dibangun.

## Status saat rencana dibuat

Fondasi backend Flask, aplikasi kasir Flutter, dan PWA menu QR telah tersedia. API kategori pengeluaran dan satuan, alur dasar inventori, serta integrasi teknis Midtrans sudah mulai diimplementasikan. Pemeriksaan terakhir menunjukkan 11 tes backend lulus, analisis dan 2 tes Flutter lulus, serta build dan lint PWA lulus.

Hal-hal tersebut belum membuktikan kesiapan produksi. Kredensial merchant, pembayaran end-to-end, push notification, pengujian iOS, beberapa operasi manajemen, dan kesiapan operasional masih perlu diselesaikan serta diverifikasi.

## Urutan pekerjaan

### 1. Tetapkan keputusan yang menghambat rilis

- [ ] Pemilik produk memilih payment gateway dan menyelesaikan pendaftaran merchant serta dokumen usaha.
- [ ] Tentukan domain produksi untuk API dan PWA, nama aplikasi, application ID/bundle ID, serta versi minimum iOS.
- [ ] Pilih dan uji model printer Bluetooth ESC/POS yang akan dipakai di outlet; tentukan prosedur jika pencetakan gagal.
- [ ] Siapkan akun Firebase, kredensial APNs untuk iOS, serta akses ke environment sandbox dan produksi gateway.
- [ ] Sepakati pemilik operasional yang menyetujui UAT, pemantauan, dan keputusan go/no-go.

**Gerbang:** jangan mengaktifkan pembayaran atau push produksi sebelum akun, domain, identitas aplikasi, dan pemilik operasional tersedia.

### 2. Tutup gap fungsi backend dan frontend

- [ ] Cocokkan seluruh layar dan alur aplikasi dengan API yang benar-benar tersedia; jangan mengandalkan nama endpoint atau dokumentasi yang belum diverifikasi.
- [ ] Lengkapi CRUD dan validasi manajemen yang dibutuhkan P0: menu, kategori, varian, modifier, channel, bahan, resep, meja/QR, pengguna, perangkat, serta operasi stok.
- [ ] Pastikan pembelian, stok opname, waste, penyesuaian, dan pengurangan stok transaksi konsisten serta tercatat di ledger.
- [ ] Lengkapi alur pengeluaran berkategori, shift/kas, laporan, dan pembatasan data laba sesuai role.
- [ ] Tinjau void/refund, pencatatan audit, pengelolaan perangkat dicabut, serta batas sesi offline 7 hari. Aksi yang belum aman atau belum tersedia jangan ditampilkan sebagai berhasil.
- [ ] Pastikan foto nota, ekspor laporan, laporan offline, dan fitur P1 diberi status lingkup yang jelas; kebutuhan P0 tidak boleh tertukar dengan fitur yang ditunda.
- [ ] Sinkronkan kontrak API dan panduan setup backend, mobile, dan PWA dengan perilaku implementasi terkini.

**Gerbang:** seluruh alur P0 dapat diselesaikan end-to-end dengan respons server yang benar dan izin yang ditegakkan backend.

### 3. Selesaikan dan validasi QRIS

- [ ] Konfigurasikan Midtrans sandbox menggunakan secret di secret manager/environment server; pastikan secret tidak masuk ke aplikasi, PWA, log, atau repository.
- [ ] Uji pembuatan tagihan dan tampilan QR dari gateway dengan nominal yang dihitung backend.
- [ ] Uji webhook signature, pencocokan order, nominal, status, dan referensi transaksi; tolak notifikasi palsu, tidak cocok, atau berulang tanpa menggandakan pembayaran/stok.
- [ ] Lengkapi dan uji status pending, dibayar, gagal, kedaluwarsa, pembatalan, serta refund sesuai alur PRD.
- [ ] Tambahkan rekonsiliasi status melalui API gateway untuk notifikasi yang terlambat/hilang dan laporan transaksi gateway.
- [ ] Uji kondisi timeout dan gangguan gateway. Pengguna harus memperoleh pesan yang jelas, pesanan tidak dinyatakan lunas secara lokal, dan pilihan tunai tetap tersedia.
- [ ] Minta gateway dan pemilik produk menyetujui pengujian end-to-end di environment sandbox sebelum berpindah ke kredensial produksi.

**Gerbang:** hanya bukti dari gateway yang sudah diverifikasi server dapat mengubah pesanan menjadi lunas; semua kasus pembayaran dan rekonsiliasi lulus uji.

### 4. Aktifkan notifikasi kasir

- [ ] Integrasikan Firebase Cloud Messaging, registrasi/pembaruan/pencabutan token perangkat, serta penargetan hanya ke perangkat kasir yang aktif.
- [ ] Lengkapi konfigurasi native Android dan iOS/APNs, izin notifikasi, serta perilaku saat aplikasi terbuka, di latar belakang, atau dibuka dari notifikasi.
- [ ] Uji suara, badge, isi notifikasi, token kedaluwarsa, perangkat dicabut, dan kegagalan pengiriman.
- [ ] Pastikan inbox pesanan tetap dimuat dari backend dan dapat diperbarui saat reconnect/refresh jika push atau WebSocket tidak diterima.

**Gerbang:** pesanan tidak hilang akibat kegagalan notifikasi dan push berfungsi pada perangkat Android serta iOS yang didukung.

### 5. Pastikan sync offline aman di Android dan iOS

- [ ] Verifikasi antrean lokal, idempotency key, retry, penanganan error, pemulihan setelah aplikasi ditutup, dan tidak adanya duplikasi transaksi.
- [ ] Uji pemicu sinkronisasi saat transaksi dibuat, aplikasi dibuka/dilanjutkan, koneksi pulih, dan pengguna menekan tombol sync.
- [ ] Uji batas sesi offline tujuh hari, katalog yang terakhir tersimpan, serta tampilan jumlah transaksi yang menunggu dan kegagalannya.
- [ ] Uji Android WorkManager pada perangkat fisik dengan pembatasan baterai dan jaringan.
- [ ] Uji iOS pada perangkat fisik untuk foreground, reconnect, dan background refresh best-effort. Jangan menjanjikan jadwal background berkala karena sistem operasi dapat menundanya.
- [ ] Dokumentasikan langkah kasir ketika sync gagal dan prosedur rekonsiliasi transaksi tertunda.

**Gerbang:** transaksi offline tersimpan lokal, tidak hilang atau terduplikasi, status antrean dapat dipahami, dan jalur foreground/reconnect/manual bekerja pada kedua platform.

### 6. Uji keamanan, kualitas, dan kompatibilitas

- [ ] Jalankan seluruh tes backend, Flutter, serta build/lint PWA di CI; tambahkan tes untuk gap atau regresi yang ditemukan.
- [ ] Uji autentikasi dan RBAC untuk Kasir, Admin/Owner, dan Super Admin pada endpoint, bukan hanya tampilan aplikasi.
- [ ] Uji skenario transaksi, stok, pembayaran, konflik perangkat ganda, retry, waktu perangkat berbeda, dan kegagalan jaringan/gateway.
- [ ] Lakukan pemeriksaan keamanan endpoint publik QR, rate limit, validasi input, kebocoran secret, keamanan webhook, dan HTTPS.
- [ ] Uji migrasi database MySQL dan Drift dari versi sebelumnya serta pemulihan database dari backup.
- [ ] Uji aplikasi pada Android/iOS, HP/tablet, portrait/landscape, serta printer dan kondisi jaringan outlet sebenarnya.
- [ ] Ukur target PRD: waktu buka offline, katalog 500 menu, ukuran sync batch, dan tidak adanya transaksi hilang/duplikat.
- [ ] Periksa dependency dan laporan kerentanan; tetapkan tindak lanjut untuk temuan yang belum dapat diperbaiki.

**Gerbang:** tidak ada defect kritis/tinggi yang belum ditangani atau diterima secara tertulis; skenario transaksi dan keamanan utama lulus.

### 7. Siapkan infrastruktur dan operasi produksi

- [ ] Siapkan MySQL 8, Redis, Flask/Gunicorn, Nginx, domain, TLS, firewall, dan konfigurasi skala/kapasitas sesuai kebutuhan outlet.
- [ ] Gunakan secret kuat dan unik untuk production; validasi konfigurasi startup dan batasi akses secret hanya kepada layanan yang memerlukan.
- [ ] Terapkan migrasi database yang ditinjau dan diuji. Buat backup otomatis, tentukan retensi, lalu lakukan uji restore sebelum rilis.
- [ ] Siapkan monitoring kesehatan API, error aplikasi, pembayaran, queue/sync, Redis, kapasitas database, dan notifikasi yang gagal.
- [ ] Pastikan log tidak menyimpan password, PIN, token, server key, atau data sensitif webhook secara tidak perlu.
- [ ] Siapkan prosedur deployment, rollback aplikasi/API/database yang kompatibel, eskalasi insiden, dan kontak dukungan.
- [ ] Ganti/hapus akun serta password demo sebelum deployment publik; buat akun awal produksi secara aman dan verifikasi hak aksesnya.

**Gerbang:** deployment dapat dipantau dan dipulihkan; backup benar-benar dapat direstore; tidak ada kredensial demo atau secret default.

### 8. UAT dan rilis bertahap

- [ ] Jalankan UAT di outlet dengan Kasir, Admin/Owner, dan Super Admin; catat hasil, bukti, serta persetujuan pemilik produk.
- [ ] Latih kasir tentang transaksi offline, pembayaran QRIS, notifikasi, pencetakan ulang, sync tertunda, dan tindakan saat gangguan.
- [ ] Lakukan deployment terbatas/internal terlebih dahulu, lalu uji transaksi nyata dengan pemantauan aktif.
- [ ] Aktifkan fitur berisiko (QRIS/push) secara bertahap setelah verifikasi konfigurasi dan hasil uji di environment yang tepat.
- [ ] Pantau error, pembayaran pending/selisih, transaksi sinkronisasi, stok, dan tiket dukungan setelah setiap tahap.
- [ ] Hentikan perluasan rilis dan jalankan rollback/mitigasi bila terjadi transaksi hilang/duplikat, pembayaran tidak cocok, atau akses tidak sah.

## Daftar go/no-go sebelum rilis publik

- [ ] Semua kebutuhan P0 pada PRD terpenuhi atau ada keputusan tertulis dari pemilik produk bahwa rilis ditunda/diubah lingkupnya.
- [ ] QRIS diuji end-to-end dan rekonsiliasi/refund memiliki prosedur operasional.
- [ ] Push diuji pada Android dan iOS; inbox tetap menjadi jalur pemulihan.
- [ ] Sinkronisasi offline, sesi tujuh hari, dan pemulihan transaksi diuji pada perangkat sasaran.
- [ ] Operasi manajemen P0, API yang dibutuhkan, dan RBAC backend telah diverifikasi.
- [ ] UAT disetujui; tidak ada defect kritis/tinggi terbuka tanpa penerimaan risiko tertulis.
- [ ] Monitoring, backup/restore, keamanan deployment, dukungan, dan rollback siap digunakan.
- [ ] Versi aplikasi, konfigurasi production, dan hasil tes yang disetujui tercatat untuk rilis.

**Keputusan rilis:** hanya pemilik produk/operasional yang berwenang memberi persetujuan go/no-go setelah seluruh gerbang terpenuhi. Jika satu gerbang P0 belum lulus, tunda rilis atau keluarkan fitur terkait dari rilis secara eksplisit; jangan menganggapnya siap hanya karena build berhasil.
