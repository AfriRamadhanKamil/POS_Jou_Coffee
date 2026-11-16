# Jou Coffee mobile POS

Flutter application for cashier and outlet administration. The first target is
Android; the same app is configured for iOS and adapts to phone and tablet
layouts.

## Run locally

1. Start the Flask API on port `5000`. For a physical Android device, connect
   the computer and phone to the same private Wi-Fi network. Use the computer's
   IPv4 address, not `127.0.0.1` or `10.0.2.2`.
2. From this directory, run `flutter pub get`.
3. Use the correct API URL:
   - Android emulator: `http://10.0.2.2:5000/api/v1`
   - Physical Android: `http://<COMPUTER-IPV4>:5000/api/v1`, for example
     `http://192.168.1.10:5000/api/v1`
   - iOS simulator: `http://127.0.0.1:5000/api/v1`
4. Run the app, replacing both example addresses with the computer's IPv4:
   ```powershell
   flutter run `
     --dart-define=API_BASE_URL=http://192.168.1.10:5000/api/v1 `
     --dart-define=QR_MENU_BASE_URL=http://192.168.1.10:5173
   ```
   Android debug builds allow local HTTP. Use HTTPS for production builds.

`API_BASE_URL` is used for login, catalog, orders, reports, management,
payments, and Socket.IO notifications. `QR_MENU_BASE_URL` is the address
embedded in table QR codes; start the PWA with
`npm.cmd run dev -- --host 0.0.0.0` and make sure customers' phones can reach
that address. See [the QR Menu README](../../qr-menu/README.md).

### Build an APK for a physical Android phone

The default API address (`10.0.2.2`) is only for the Android emulator. To build
an APK for a phone, replace `192.168.1.10` below with the computer's Wi-Fi IPv4
address from `ipconfig`, then run this from the `mobile` directory:

```powershell
flutter build apk --debug --target-platform android-arm64 `
  --dart-define=API_BASE_URL=http://192.168.1.10:5000/api/v1 `
  --dart-define=QR_MENU_BASE_URL=http://192.168.1.10:5173
```

The APK is written to
`build\app\outputs\flutter-apk\app-debug.apk`. Copy it to the phone and open it
to install, or connect the phone with USB debugging enabled and run
`adb install .\build\app\outputs\flutter-apk\app-debug.apk`. The phone and
computer must be on the same trusted private Wi-Fi network, and the API health
URL (`http://<COMPUTER-IPV4>:5000/api/v1/health`) must open in the phone's
browser. If the computer's IP or network changes, rebuild the APK with its new
IP. This debug APK allows local HTTP for development only; production builds
must use HTTPS.

The app stores the last successful menu catalog and unsynchronized POS orders
in persistent Drift/SQLite on the device. Offline POS orders remain visible in
the POS sync queue with their amount and any sync error. Pending orders are
retried against the idempotent
`POST /api/v1/orders` endpoint when the cashier manually syncs or returns to
the app; Android also schedules a network-constrained 15-minute WorkManager
retry. This direct order retry is intentional: the current backend
`/sync/push` endpoint only records change-log rows and does not create POS
orders. The backend uses the MySQL/MariaDB database configured for the local
XAMPP environment; tests use a separate in-memory SQLite database. Offline
SQLite currently covers the cached POS catalog and pending POS transactions;
management and online-only features still require a server connection.

Bluetooth ESC/POS receipt printing, QR generation for table setup, and
Socket.IO notifications are wired into the app. iOS currently retries
synchronization when the app returns to the foreground; periodic iOS background
execution and Firebase push notifications require native project configuration
and are not enabled by the starter project.
