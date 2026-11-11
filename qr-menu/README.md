# Jou Coffee QR Menu

QR menu web app for customers. It is built with React, TypeScript, Vite, and a
PWA service worker. It opens from a table QR token at `/<token>` or with
`/?token=<token>`.

## Run locally

1. Start the Flask API at `http://127.0.0.1:5000`.
2. Run `npm.cmd install`.
3. Copy `.env.example` to `.env.local` if the API is hosted at another URL.
4. Run `npm.cmd run dev`.

The Vite development server proxies `/api/v1` to the local Flask server. For a
deployed app, set `VITE_API_BASE_URL` to the API base URL ending in `/api/v1`.

The PWA caches the application shell only. The menu, order, and payment status
always require a live API response; the web app never treats a payment as paid
based on browser state. The repository's current QRIS endpoint returns a demo
charge payload; connect the chosen payment gateway before using QRIS in
production.
