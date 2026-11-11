# Jou Coffee QR Menu

QR menu web app for customers. It is built with React, TypeScript, Vite, and a
PWA service worker. It opens from a table QR token at `/<token>` or with
`/?token=<token>`.

## Run locally

1. Start the Flask API on the development computer at port `5000`.
2. Run `npm.cmd install`.
3. Run `npm.cmd run dev -- --host 0.0.0.0` to make the menu reachable from a
   phone on the same private Wi-Fi network. Open the Vite URL shown in the
   terminal using the computer's IPv4 address.

The Vite development server proxies `/api/v1` to the Flask API on the computer,
so the phone's browser does not need a separate API URL. For a deployed app, set
`VITE_API_BASE_URL` to the API base URL ending in `/api/v1`.

The PWA caches the application shell only. The menu, order, and payment status
always require a live API response; the web app never treats a payment as paid
based on browser state. QRIS checkout requires valid Midtrans sandbox
credentials for local testing and production credentials plus a completed
end-to-end verification before public release.
