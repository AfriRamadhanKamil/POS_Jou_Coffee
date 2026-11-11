# 🗂️ Backend Development Plan — POS Jou Coffee

> Planning document untuk implementasi backend POS Jou Coffee.
> Fokus: **Backend only** (Flask REST API + MySQL).
> Target audience: Junior developer / AI model untuk implementasi.

---

## Tech Stack & Dependencies

| Komponen | Teknologi |
|---|---|
| Framework | **Flask** (Python) |
| ORM | **SQLAlchemy** |
| Migration | **Alembic** |
| Auth | **Flask-JWT-Extended** |
| Serialization/Validation | **Marshmallow** |
| Realtime | **Flask-SocketIO** |
| Server | **Gunicorn** (gevent worker) + **Nginx** |
| Database | **MySQL 8** (InnoDB, utf8mb4) |
| Cache & Pub/Sub | **Redis** |
| Password Hashing | **Argon2** atau **bcrypt** |

### Setup Awal

```
pip install flask sqlalchemy alembic flask-jwt-extended marshmallow flask-socketio gunicorn redis argon2-cffi flask-cors
```

---

## Issue #1 — Project Setup & Struktur Folder

**Deskripsi:**
Buat skeleton project Flask dengan struktur blueprint-based, konfigurasi environment, dan koneksi database.

**Yang perlu dilakukan:**
- Inisialisasi project Flask dengan pattern **Application Factory** (`create_app()`)
- Buat struktur folder berbasis **Blueprint** (setiap modul = 1 blueprint)
- Setup file konfigurasi (`config.py`) untuk dev, testing, dan production
- Setup koneksi **SQLAlchemy** ke MySQL dan **Redis**
- Inisialisasi **Alembic** untuk database migration
- Buat `.env.example` dengan variabel yang dibutuhkan (DB URL, JWT secret, Redis URL, dll)
- Buat `requirements.txt` atau `pyproject.toml`
- Setup **CORS** untuk akses dari QR menu web

**Struktur folder yang diharapkan:**
```
backend/
├── app/
│   ├── __init__.py          # create_app()
│   ├── config.py
│   ├── extensions.py        # db, jwt, socketio, marshmallow, redis
│   ├── auth/                # blueprint
│   ├── catalog/             # blueprint
│   ├── inventory/           # blueprint
│   ├── orders/              # blueprint
│   ├── finance/             # blueprint
│   ├── reports/             # blueprint
│   ├── sync/                # blueprint
│   ├── users/               # blueprint
│   ├── public/              # blueprint (QR menu endpoints)
│   ├── realtime/            # socketio events
│   └── common/              # helpers, decorators, error handlers
├── migrations/              # alembic
├── tests/
├── .env.example
├── requirements.txt
└── run.py
```

---

## Issue #2 — Database Models & Migration

**Deskripsi:**
Buat semua SQLAlchemy models sesuai desain database di PRD dan jalankan migration pertama.

**Yang perlu dilakukan:**
- Semua model pakai **UUID** (`CHAR(36)`) sebagai primary key
- Semua model yang disinkronkan wajib punya kolom standar: `id`, `created_at`, `updated_at`, `deleted_at` (soft delete), `created_by`, `device_id`, `server_version` (BIGINT, auto-increment oleh server)
- Uang pakai `DECIMAL(15,2)`, kuantitas stok pakai `DECIMAL(15,4)`, semua waktu **UTC**

**Grup tabel yang perlu dibuat:**

| Grup | Tabel |
|---|---|
| Akses | `users`, `devices`, `audit_logs` |
| Katalog | `categories`, `menus`, `menu_variants`, `modifier_groups`, `modifiers`, `sales_channels`, `menu_channel_prices` |
| Inventori | `units`, `ingredients`, `recipes`, `recipe_items`, `stock_movements`, `stock_balances`, `stock_opnames`, `stock_opname_items`, `purchases`, `purchase_items` |
| Transaksi | `tables`, `orders`, `order_items`, `order_item_modifiers`, `payments`, `order_status_logs` |
| Keuangan | `expense_categories`, `expenses`, `cash_shifts`, `cash_movements` |
| Sistem | `notifications`, `settings`, `sync_changes` |

- Buat index di kolom: `created_at`, `status`, `server_version`
- Buat unique constraint di: `order_no`, `idempotency_key`
- Jalankan `alembic upgrade head` untuk verifikasi

---

## Issue #3 — Authentication & Authorization (RBAC)

**Deskripsi:**
Implementasi sistem login, JWT token, role-based access control, dan PIN kasir.

**Endpoints:**
- `POST /api/v1/auth/login` — login dengan username & password, return access + refresh token
- `POST /api/v1/auth/refresh` — refresh access token
- `POST /api/v1/auth/logout` — invalidate token
- `POST /api/v1/auth/verify-pin` — verifikasi PIN 6 digit kasir

**Yang perlu dilakukan:**
- Password di-hash dengan **Argon2** atau **bcrypt**
- Access token **15 menit**, refresh token lebih lama
- JWT claims harus include `role` dan `user_id`
- Buat **decorator** RBAC (contoh: `@role_required('admin', 'super_admin')`) yang mengecek role dari JWT claims
- PIN kasir di-hash juga, digunakan untuk login cepat dan approval aksi sensitif (void, diskon di atas batas)
- Saat login, **device_id** dicatat. Batas perangkat aktif per user = configurable (default 3)
- Admin bisa mencabut perangkat (`DELETE /api/v1/devices/{id}`)

---

## Issue #4 — User & Device Management

**Deskripsi:**
CRUD user dan device management sesuai hak akses role.

**Endpoints:**
- `GET/POST/PATCH/DELETE /api/v1/users` — kelola akun
- `GET/DELETE /api/v1/devices` — lihat dan cabut perangkat
- `GET /api/v1/audit-logs` — Super Admin only

**Aturan akses:**
- **Admin** bisa CRUD akun **Kasir** saja (hanya 1 akun kasir)
- **Super Admin** bisa CRUD akun **Admin** dan **Kasir**
- Audit log mencatat aksi sensitif: void, hapus, ubah harga, ubah stok, ubah izin

---

## Issue #5 — Catalog Management (Menu, Kategori, Modifier)

**Deskripsi:**
CRUD untuk menu, kategori, varian, modifier, channel, dan harga per channel.

**Endpoints:**
- `GET /api/v1/menus/catalog` — semua role, read-only (untuk POS)
- `CRUD /api/v1/menus` — Admin ke atas
- `CRUD /api/v1/categories` — Admin ke atas
- `CRUD /api/v1/modifiers` — Admin ke atas (termasuk modifier groups)
- `CRUD /api/v1/channels` — Admin ke atas (sales channels)

**Yang perlu dilakukan:**
- Menu punya: nama, kategori, foto, status aktif/nonaktif, varian (ukuran dll), modifier (topping dll) dengan harga tambahan
- Harga bisa berbeda per channel (GoFood, GrabFood, dll) via `menu_channel_prices`
- Endpoint catalog mengembalikan semua data yang dibutuhkan POS dalam 1 call
- Item yang stoknya habis ditandai dengan flag `is_available`
- Soft delete (jangan hapus fisik)

---

## Issue #6 — Inventory Management (Bahan Baku, Resep, Stok)

**Deskripsi:**
CRUD bahan baku, resep/BOM, dan pencatatan pergerakan stok.

**Endpoints:**
- `CRUD /api/v1/ingredients` — bahan baku
- `CRUD /api/v1/recipes` — resep (BOM: menu/varian → daftar bahan + takaran)
- `POST /api/v1/stock/movements` — catat stok masuk, penyesuaian, waste
- `POST /api/v1/stock/opname` — stok opname
- `CRUD /api/v1/purchases` — pembelian bahan baku

**Yang perlu dilakukan:**
- Stok disimpan sebagai **ledger** (`stock_movements`) dengan tipe: PURCHASE, SALE, ADJUSTMENT, WASTE, OPNAME, VOID_REVERSAL
- `stock_balances` menyimpan saldo terkini per bahan baku (dihitung dari movements)
- HPP dihitung otomatis dari resep × harga beli terakhir bahan
- Stok **boleh minus** dan ditandai untuk audit
- Endpoint hanya untuk Admin ke atas

---

## Issue #7 — Order & Transaction

**Deskripsi:**
Endpoint untuk membuat pesanan (POS, online platform), update status, pembayaran, dan void/refund.

**Endpoints:**
- `POST /api/v1/orders` — buat pesanan baru
- `PATCH /api/v1/orders/{id}/status` — update status (PREPARING, READY, COMPLETED)
- `POST /api/v1/orders/{id}/payments` — catat pembayaran
- `POST /api/v1/orders/{id}/void` — void/refund (butuh PIN Admin)

**Yang perlu dilakukan:**
- Order punya atribut: `source` (POS/QR/ONLINE_PLATFORM), `order_type` (DINE_IN/TAKE_AWAY/DELIVERY), `status`, `payment_status`
- Generate `order_no` dengan format: `JOU-{kode_device}-{tanggal}-{urut}` (contoh: JOU-K01-20261102-0007)
- Pesanan POS langsung berstatus **APPROVED**
- Saat APPROVED: stok dipotong otomatis sesuai resep (`stock_movements` tipe SALE)
- Saat void: stok dikembalikan via movement lawan (VOID_REVERSAL), **bukan** hapus data
- Diskon per item atau per transaksi (nominal atau persen), tanpa PPN
- Pesanan online: catat `channel_id`, `external_order_id`, komisi (%), pendapatan kotor/bersih. Metode bayar "Platform" tidak masuk kas
- Catat setiap perubahan status di `order_status_logs`

---

## Issue #8 — QR Menu Public API

**Deskripsi:**
Endpoint publik (tanpa JWT) untuk pelanggan yang memesan lewat QR menu.

**Endpoints:**
- `GET /api/v1/public/qr/{token}/menu` — lihat menu aktif berdasarkan token meja
- `POST /api/v1/public/qr/{token}/orders` — buat pesanan dari QR
- `GET /api/v1/public/orders/{id}/status` — tracking status pesanan
- `POST /api/v1/public/orders/{id}/pay` — buat tagihan QRIS dinamis
- `POST /api/v1/public/payments/webhook` — callback dari payment gateway

**Yang perlu dilakukan:**
- Token meja harus **bertanda tangan** (signed) dan bisa di-regenerate oleh Admin
- **Rate limit** per IP dan per meja untuk proteksi spam
- Pesanan tunai → status `PENDING_APPROVAL`, kirim notifikasi ke semua perangkat kasir (via SocketIO + FCM)
- Pesanan QRIS → status `AWAITING_PAYMENT`, buat tagihan QRIS dinamis via payment gateway API
- Webhook handler: verifikasi **tanda tangan** dari gateway, cocokkan ID tagihan dan nominal, lalu update `payment_status` = PAID dan `status` = APPROVED. Handler harus **idempoten**
- Server cek ketersediaan menu/stok **sebelum** tagihan dibuat
- Pesanan yang tidak direspons/dibayar > N menit (default 10) → status `EXPIRED`
- **JANGAN** terima perubahan status PAID dari browser pelanggan, hanya dari webhook

---

## Issue #9 — QR Order Approval (Kasir)

**Deskripsi:**
Endpoint untuk kasir meng-approve/reject pesanan QR yang bayar tunai.

**Endpoints:**
- `GET /api/v1/orders/pending-approval` — list pesanan menunggu approval
- `POST /api/v1/orders/{id}/approve` — terima pesanan (bisa edit item dulu)
- `POST /api/v1/orders/{id}/reject` — tolak pesanan (alasan wajib diisi)

**Yang perlu dilakukan:**
- Saat approve: status → APPROVED, stok dipotong, masuk laporan
- Saat reject: status → REJECTED, alasan dicatat, pelanggan diarahkan ke kasir
- Kirim notifikasi realtime ke kasir saat ada pesanan baru (SocketIO)
- Handle race condition: jika 2 perangkat approve pesanan yang sama, yang pertama menang, perangkat lain diberi tahu

---

## Issue #10 — Finance (Kas, Shift, Pengeluaran)

**Deskripsi:**
Endpoint untuk manajemen kas harian, shift kasir, dan pengeluaran.

**Endpoints:**
- `GET/POST /api/v1/shifts` — buka dan tutup shift
- `GET/POST /api/v1/cash-movements` — kas masuk/keluar
- `GET/POST/PATCH/DELETE /api/v1/expenses` — pengeluaran

**Yang perlu dilakukan:**
- Shift: buka dengan modal awal, catat kas masuk/keluar selama shift, tutup shift dengan hitung selisih (expected vs actual)
- Pengeluaran: kategori, nominal, catatan, foto nota. Kasir bisa lihat + tambah, Admin bisa CRUD
- Summary kas: hanya pembayaran tunai berstatus PAID yang masuk kas laci. QRIS dan Platform dicatat sebagai non-tunai

---

## Issue #11 — Reports & Charts

**Deskripsi:**
Endpoint laporan penjualan, summary kas, grafik, dan laba.

**Endpoints:**
- `GET /api/v1/reports/sales` — laporan harian/mingguan/bulanan
- `GET /api/v1/reports/cash-summary` — summary kas
- `GET /api/v1/reports/charts` — data grafik
- `GET /api/v1/reports/profit` — laba kotor (Admin ke atas)

**Yang perlu dilakukan:**
- Filter: tipe pesanan, channel, metode bayar, kasir, rentang tanggal
- Laporan menghitung order berstatus **APPROVED ke atas** yang **tidak dibatalkan**
- Grafik: penjualan per hari, per jam, menu terlaris, per channel, per tipe pesanan
- Laba kotor = pendapatan − HPP (dari resep). Hanya untuk Admin/Owner dan Super Admin
- Ekspor **PDF** dan **Excel** (P1, bisa ditunda)
- Kasir bisa lihat laporan tapi **tanpa HPP dan laba**

---

## Issue #12 — Sync Engine (Offline-Online)

**Deskripsi:**
Endpoint sinkronisasi data antara perangkat mobile (SQLite) dan server (MySQL).

**Endpoints:**
- `POST /api/v1/sync/push` — perangkat mengirim data baru/update ke server (batch)
- `GET /api/v1/sync/pull?cursor=N` — perangkat menarik perubahan dari server sejak cursor terakhir

**Yang perlu dilakukan:**
- Push: terima batch data, proses satu per satu, tolak duplikat berdasarkan **idempotency_key**
- Pull: kirim semua record yang `server_version > cursor`. Gunakan `server_version` (auto-increment BIGINT) sebagai cursor
- Konflik master data: **server menang** (last-write-wins berdasarkan `server_version`)
- Transaksi **append-only**, koreksi lewat void/refund baru
- Stok dihitung di server dari ledger `stock_movements`, bukan saling timpa
- Catat `device_id` dan deteksi selisih jam perangkat > 5 menit

---

## Issue #13 — Realtime Notification (WebSocket)

**Deskripsi:**
Setup WebSocket untuk notifikasi realtime ke perangkat kasir.

**Yang perlu dilakukan:**
- Setup **Flask-SocketIO** dengan **Redis** sebagai message queue (agar support multi-worker Gunicorn)
- Namespace/channel: `orders` — untuk notifikasi pesanan QR baru, perubahan status
- Kirim event saat: pesanan QR baru masuk, pembayaran QRIS diterima, pesanan di-approve/reject
- Auth WebSocket via JWT token
- Siapkan juga integrasi **FCM** untuk push notification saat app di background (bisa pakai library `pyfcm` atau Firebase Admin SDK)

---

## Issue #14 — Table & QR Management

**Deskripsi:**
CRUD meja dan generate QR code untuk QR menu.

**Endpoints:**
- `CRUD /api/v1/tables` — kelola meja (Admin ke atas)
- Regenerate QR token per meja

**Yang perlu dilakukan:**
- Setiap meja punya `token` unik yang **signed** (gunakan HMAC atau JWT)
- Token bisa di-regenerate oleh Admin (invalidate token lama)
- QR code berisi URL: `{base_url}/qr/{token}`

---

## Urutan Pengerjaan (Roadmap Backend)

Kerjakan sesuai urutan ini karena ada dependensi antar issue:

```
Phase 1 — Fondasi
  └── Issue #1: Project Setup
  └── Issue #2: Database Models & Migration

Phase 2 — Auth & Core
  └── Issue #3: Authentication & RBAC
  └── Issue #4: User & Device Management

Phase 3 — Business Logic
  └── Issue #5: Catalog Management
  └── Issue #6: Inventory Management
  └── Issue #7: Order & Transaction

Phase 4 — QR Menu & Realtime
  └── Issue #13: Realtime Notification (WebSocket) ← sebelum QR
  └── Issue #8: QR Menu Public API
  └── Issue #9: QR Order Approval
  └── Issue #14: Table & QR Management

Phase 5 — Finance & Reports
  └── Issue #10: Finance (Kas, Shift, Pengeluaran)
  └── Issue #11: Reports & Charts

Phase 6 — Sync
  └── Issue #12: Sync Engine
```

---

## Catatan Penting untuk Implementor

1. **Semua endpoint non-publik wajib pakai JWT** dan dicek role-nya di server (RBAC). Jangan hanya sembunyi di UI.
2. **Soft delete** — jangan pernah hapus data fisik, gunakan `deleted_at`.
3. **UUID** sebagai primary key di semua tabel yang disinkronkan.
4. **Idempotency** — sync push dan webhook handler harus idempoten.
5. **Validasi input** di setiap endpoint menggunakan Marshmallow schema.
6. **Rate limit** di endpoint publik (QR menu).
7. **HTTPS** wajib di production.
8. **Environment variable** untuk semua secret (JWT key, DB password, API key gateway). Jangan hardcode.
9. Semua response API gunakan format konsisten, contoh: `{ "success": true, "data": {...}, "message": "..." }`.
10. Prefix semua endpoint: `/api/v1/`.
<<<<<<< HEAD

=======
>>>>>>> 0c785a0 (feat(backend): implement Flask REST API, models, and tests for POS Jou Coffee (fixes #2))
