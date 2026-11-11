# Jou Coffee mobile POS

Flutter application for cashier and outlet administration. The first target is
Android; the same app is configured for iOS and adapts to phone and tablet
layouts.

## Run locally

1. Start the Flask API on port `5000`.
2. From this directory, run `flutter pub get`.
3. Run `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000/api/v1
   --dart-define=QR_MENU_BASE_URL=http://10.0.2.2:5173` for an Android emulator.
   Use the reachable API and web hosts for a physical device. For an iOS
   simulator, use `http://127.0.0.1:5000/api/v1` and
   `http://127.0.0.1:5173`.

The app stores the last successful menu catalog and unsynchronized POS orders
in Drift/SQLite. Pending orders are retried against the idempotent
`POST /api/v1/orders` endpoint when the cashier manually syncs or returns to
the app; Android also schedules a network-constrained 15-minute WorkManager
retry. This direct order retry is intentional: the current backend
`/sync/push` endpoint only records change-log rows and does not create POS
orders.

Bluetooth ESC/POS receipt printing, QR generation for table setup, and
Socket.IO notifications are wired into the app. iOS currently retries
synchronization when the app returns to the foreground; periodic iOS background
execution and Firebase push notifications require native project configuration
and are not enabled by the starter project.
