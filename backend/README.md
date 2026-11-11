# ☕ POS Jou Coffee — Backend API (Flask + MySQL)

Backend REST API & Realtime WebSocket service untuk **Jou Coffee POS**, dirancang dengan arsitektur **Offline-First**, Role-Based Access Control (**RBAC**), dan integrasi **QR Menu** + **Payment Gateway**.

---

## 🛠️ Tech Stack

- **Framework:** Python Flask (Application Factory & Blueprints)
- **Database:** MySQL 8 (InnoDB, utf8mb4) & SQLite (testing/local fallback)
- **ORM & Migrations:** SQLAlchemy 2.0 & Alembic / Flask-Migrate
- **Authentication:** Flask-JWT-Extended (15-min access token, refresh token, role claims)
- **Realtime:** Flask-SocketIO (WebSocket dengan Redis pub/sub)
- **Password & PIN Hash:** Argon2 / Scrypt (Werkzeug Security)
- **Server:** Gunicorn (gevent worker) + Nginx

---

## 📁 Struktur Direktori

```
backend/
├── app/
│   ├── __init__.py          # create_app() factory, error handlers, extensions init
│   ├── config.py            # Development, Testing, Production configurations
│   ├── extensions.py        # db, jwt, socketio, marshmallow, cors
│   ├── models.py            # Model registry for Alembic & DB reflection
│   ├── auth/                # Login, refresh token, PIN verification, devices, audit logs
│   ├── users/               # User CRUD (Kasir, Admin, Super Admin) & Device revoke
│   ├── catalog/             # POS Catalog, Menu, Categories, Modifiers, Sales Channels
│   ├── inventory/           # Units, Ingredients, BOM Recipes, Stock Movements, Opname, Purchases
│   ├── orders/              # Orders, Payments, Void (Admin PIN), Status Logs, QR Cash Approval
│   ├── public/              # Public QR Menu API, Dynamic QRIS payment, Webhook handler
│   ├── finance/             # Cash Shifts (buka/tutup shift), Cash In/Out, Expenses
│   ├── reports/             # Sales reports, Cash summary, Charts, Profit (COGS/HPP)
│   ├── tables/              # Table management & Signed QR token regeneration
│   ├── sync/                # Offline-Online Sync Engine (Push batch, Pull cursor)
│   ├── realtime/            # WebSocket socketio events & rooms
│   └── common/              # Base model, RBAC decorators, response wrappers
├── tests/
│   └── test_api.py          # Pytest suite untuk auth, catalog, order, QR, approval
├── .env.example             # Template konfigurasi environment
├── requirements.txt         # Daftar dependencies
├── run.py                   # Entry point aplikasi
└── seed.py                  # Initial database seeder
```

---

## 🚀 Quick Start Guide

### 1. Inisialisasi Virtual Environment & Install Dependencies

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Konfigurasi Environment Variable

Salin `.env.example` menjadi `.env`:
```powershell
copy backend\.env.example backend\.env
```
Sesuaikan `DATABASE_URL` (default ke SQLite untuk testing lokal, atau gunakan MySQL 8 di production).

Production menolak konfigurasi yang tidak memiliki `DATABASE_URL` MySQL, `REDIS_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, `QR_HMAC_SECRET`, dan `PAYMENT_GATEWAY_SERVER_KEY`. Secret aplikasi harus memiliki sedikitnya 32 karakter. Gunakan kredensial merchant Midtrans yang sesuai dengan environment dan simpan seluruh secret di environment/server secret manager, bukan di repository.

### 3. Seed Database Awal

Jalankan script seeder untuk membuat tabel dan data akun awal:
```powershell
python backend/seed.py
```

Data akun bawaan:
- **Super Admin:** `username: superadmin`, `password: superadmin123`, `PIN: 999999`
- **Admin/Owner:** `username: admin`, `password: admin123`, `PIN: 123456`
- **Kasir:** `username: kasir`, `password: kasir123`, `PIN: 654321`

Akun tersebut hanya untuk development/demo. Ganti atau hapus sebelum production dan jangan gunakan kredensial contoh untuk deployment publik.

### 4. Menjalankan Server Development

```powershell
python backend/run.py
```
Server akan berjalan di `http://127.0.0.1:5000` (atau port yang diset pada `PORT`).

### 5. Menjalankan Unit Tests

```powershell
pytest backend/tests
```

---

## 🔒 Hak Akses Role (RBAC)

| Modul | Kasir | Admin/Owner | Super Admin |
|---|:---:|:---:|:---:|
| **POS & Order** | ✔ | ✔ | ✔ |
| **Approval Pesanan QR** | ✔ | ✔ | ✔ |
| **Katalog Menu** | Read-Only | CRUD | CRUD |
| **Bahan Baku & Resep** | ✖ | CRUD | CRUD |
| **Stok (Masuk, Opname, Waste)** | ✖ | CRUD | CRUD |
| **Shift & Kas Laci** | ✔ | ✔ | ✔ |
| **Pengeluaran** | Lihat + Tambah | CRUD | CRUD |
| **Laporan Penjualan & Grafik** | Lihat (tanpa laba) | Lihat + Laba | Lihat + Laba |
| **Akun Kasir** | ✖ | CRUD (Maks 1) | CRUD |
| **Akun Admin** | ✖ | ✖ | CRUD |
| **Audit Logs & Perangkat** | ✖ | Cabut Perangkat | Audit Log + Semua |

---

## 📡 Daftar Endpoint API Utama (`/api/v1`)

### 1. Auth & Pengguna
- `POST /api/v1/auth/login` — Login username/password + device registration
- `POST /api/v1/auth/refresh` — Refresh expired access token
- `POST /api/v1/auth/verify-pin` — Verifikasi 6-digit PIN kasir/admin
- `GET/POST/PATCH/DELETE /api/v1/users` — Kelola pengguna sesuai hierarki role
- `GET/DELETE /api/v1/devices` — Kelola & cabut perangkat kasir

### 2. POS & Katalog
- `GET /api/v1/menus/catalog` — Katalog lengkap untuk UI POS kasir (1 call)
- `POST /api/v1/orders` — Buat pesanan (POS / Online Channel)
- `PATCH /api/v1/orders/{id}/status` — Ubah status (PREPARING, READY, COMPLETED)
- `POST /api/v1/orders/{id}/payments` — Catat pembayaran tunai / QRIS statis
- `POST /api/v1/orders/{id}/void` — Void transaksi (wajib PIN Admin, auto-revert stok)

### 3. QR Menu (Publik & Kasir)
- `GET /api/v1/public/qr/{token}/menu` — Buka menu via QR meja tanpa login
- `POST /api/v1/public/qr/{token}/orders` — Kirim pesanan QR pelanggan
- `GET /api/v1/public/orders/{id}/status` — Cek status pesanan pelanggan
- `POST /api/v1/public/orders/{id}/pay` — Generate tagihan QRIS dinamis via Payment Gateway
- `POST /api/v1/public/payments/webhook` — Webhook otomatis terverifikasi dari gateway
- `GET /api/v1/orders/pending-approval` — Inbox pesanan QR tunai untuk kasir
- `POST /api/v1/orders/{id}/approve` — Kasir terima pesanan (auto-potong stok)
- `POST /api/v1/orders/{id}/reject` — Kasir tolak pesanan dengan alasan wajib

### 4. Inventori & Resep
- `GET/POST /api/v1/ingredients` — Master bahan baku & saldo stok
- `GET/POST /api/v1/recipes` — Resep (Bill of Materials) & kalkulasi otomatis HPP
- `POST /api/v1/stock/movements` — Catat waste / penyesuaian stok
- `POST /api/v1/stock/opname` — Stok opname & auto-balancing
- `POST /api/v1/purchases` — Pembelian bahan baku

### 5. Keuangan & Laporan
- `POST /api/v1/shifts/open` & `POST /api/v1/shifts/{id}/close` — Buka/tutup shift kasir
- `GET /api/v1/shifts/current` — Ringkasan kas laci shift aktif
- `GET/POST /api/v1/expenses` — Catat pengeluaran operasional
- `GET /api/v1/reports/sales` — Laporan penjualan dengan filter tanggal & channel
- `GET /api/v1/reports/cash-summary` — Rekapitulasi kas vs non-tunai
- `GET /api/v1/reports/charts` — Grafik menu terlaris & tipe pesanan
- `GET /api/v1/reports/profit` — Laporan laba kotor (Omzet − HPP) [Khusus Admin/Super Admin]

### 6. Offline-Online Sync
- `POST /api/v1/sync/push` — Batch push dari SQLite mobile (idempoten via `idempotency_key`)
- `GET /api/v1/sync/pull?cursor=N` — Incremental pull data sejak `server_version` terakhir
