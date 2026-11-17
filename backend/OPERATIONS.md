# Production Operations

This runbook is a deployment template. Replace example hostnames and paths, and validate it in staging before production.

## Required production configuration

Set `FLASK_ENV=production`, MySQL `DATABASE_URL`, `REDIS_URL`, strong `SECRET_KEY`, `JWT_SECRET_KEY`, `QR_HMAC_SECRET`, `PAYMENT_GATEWAY_SERVER_KEY`, and comma-separated HTTPS `CORS_ORIGINS`. The API refuses wildcard/non-HTTPS CORS origins, non-Redis rate-limit storage, and direct non-HTTPS requests. `ProxyFix` trusts one reverse proxy hop; keep the Gunicorn port private to Nginx.

Set `PAYMENT_GATEWAY_BASE_URL` to the merchant's production endpoint only after sandbox verification. Keep payment and Firebase service-account secrets outside the repository. `FCM_SERVICE_ACCOUNT_FILE` and `SENTRY_DSN` are optional; without FCM, orders remain accessible in the cashier inbox.

## Application and reverse proxy

Run one Gunicorn worker per instance with threaded Socket.IO support; scale out with Redis pub/sub and a shared rate-limit Redis store:

```sh
gunicorn --worker-class gthread --workers 1 --threads 100 --bind 127.0.0.1:8000 run:app
```

Configure Nginx for TLS, forward `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`, and enable HTTP/1.1 WebSocket upgrade on `/socket.io/`. Restrict access to port 8000 to Nginx. Use a process supervisor to restart Gunicorn and rotate application logs.

## Daily MySQL backup and restore drill

1. Store a MySQL client option file outside the repository (for example `/etc/jou-coffee/backup.cnf`) with least-privilege backup credentials and mode `0600`.
2. Schedule a daily backup; use an encrypted, access-controlled off-host destination and a retention policy approved by the business:

   ```sh
   mysqldump --defaults-extra-file=/etc/jou-coffee/backup.cnf \
     --single-transaction --routines --triggers --events jou_coffee \
     | gzip > "/secure-backups/jou_coffee-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
   ```

3. Periodically restore a selected backup into an isolated staging database, never over the live database:

   ```sh
   gunzip -c /secure-backups/<backup-file>.sql.gz \
     | mysql --defaults-extra-file=/etc/jou-coffee/restore.cnf jou_coffee_restore
   ```

4. Record backup age, restore duration, and verification results. Check schema/migration state, health, representative orders/payments, and inventory ledger totals. Do not mark the restore drill complete based only on a successful dump command.

## Monitoring, load test, and UAT

- Configure `SENTRY_DSN` and a production `SENTRY_ENVIRONMENT` to enable Flask error capture; the SDK is configured not to send default PII.
- Alert on failed health checks, database/Redis errors, payment webhook failures, repeated sync conflicts, and stale backups. Keep operational logs access-controlled.
- Before launch, run a staging load test with multiple authenticated devices creating transactions and pushing/pulling sync batches; check duplicate prevention, response latency, Redis/database saturation, and recovery after worker restart.
- Complete owner-led outlet UAT for cashier approval, shift close, QR payment, refunds/voids, and offline sync. Record sign-off and rollback steps before release.

Real gateway settlement/reconciliation and production UAT require merchant credentials, a reachable webhook URL, and owner participation; these must be verified in the target environment.
