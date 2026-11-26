# Hosting guide walkthrough

`docs/HOSTING.md` was followed step by step on 2026-11-18 from a fresh clone of `main` (the tree of `a6dc195`; the
history was rewritten after the walkthrough), on Windows 11 with Docker Engine 26.1.4 and Compose 2.27.1 (Docker Desktop). Every command in the guide was run as written. Stand-ins played the
host's own services, each in its own container on its own ports, next to (and separate from) the explore stack:

| The guide asks for | The walk used |
|---|---|
| PostgreSQL 17 | `postgres:17.11`, published on `127.0.0.1:5440` |
| S3-compatible storage | `rustfs/rustfs:1.0.4` (the explore stack's S3 server), on `127.0.0.1:9100` |
| An SMTP server | `axllent/mailpit:v1.32.0`: SMTP on `127.0.0.1:1026`, inbox on `127.0.0.1:8126` |
| An HTTPS reverse proxy | `caddy:2.10.0` with `tls internal` (Caddy's own CA), on `127.0.0.1:8443`: `scholarsync.localhost` to the app, `storage.scholarsync.localhost` to the bucket |

The app containers reached the stand-ins through `host.docker.internal`. The browser checks used Playwright with the
local CA's certificate errors ignored. The scratch clone, containers, network and volumes were removed afterwards.

## Steps

| Guide step | Result |
|---|---|
| 1. Delete the demo | Worked: `git switch -c hosting`, `git rm -r apps/demo`, commit. |
| 2. Create `.env` | Worked: copied `.env.example` and set every value in the table. Every variable the guide names exists in `.env.example`. `APP_PORT=8100` kept clear of the explore stack. |
| 2a. Operator and pages | Worked: `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL` set; the privacy page shows them. |
| 4. PostgreSQL | Worked: an empty database and owner, reached at `DATABASE_URL`. |
| 4. Storage | Worked: the guide's three AWS CLI commands (create the bucket, CORS from `cors.json`, the `pending/` lifecycle rule); the lifecycle rule reads back. **Found:** with the site on HTTPS, the browser blocks uploads to a plain-HTTP bucket endpoint (mixed content), so the public endpoint must be HTTPS too. The guide now says so, and `docs/examples/Caddyfile` shows a bucket behind the same proxy. |
| 4. SMTP | Worked: `EMAIL_URL=smtp://…`; the signup confirmation arrived in the inbox with an `https://` link from `SITE_URL`. |
| 5. Build and run | Worked: `docker compose -f compose.production.yaml up -d --build` built `scholarsync:production`, migrated, and `web` turned healthy. Plain HTTP to the app port answers `301`. Through the proxy, `/` carries an enforced `Content-Security-Policy` naming the bucket origin, and HSTS. |
| 6. Background jobs | Worked: the worker cycles (`Outbox: 0 sent, 0 failed.`). |
| 7. Deploy check | Worked: `System check identified no issues`; `/healthz` over HTTPS answers `{"ok": true}`. |
| 8. First accounts | Worked: `create_office_admin --no-input` with `OFFICE_ADMIN_PASSWORD`; the office signs in and lands on `/office/`. `seed_programs`: "2 program(s), 9 tier(s), 28 document(s), 3 school(s), 3 term(s) created."; the office sees them. |
| A student | Worked: signs up, confirms by the emailed link, signs in, uploads a photo (presigned PUT through the proxy, confirmed, shown back). No browser console errors. |
| Secrets in logs | Worked: a request to `/accounts/claim/<token>/` with the same URL as Referer logs `/accounts/claim/[redacted]/` in both the access log and the app's "Not Found" line; the token appears nowhere in the logs. |
| 9. Backups | `pg_dump --format=custom` worked. **Found:** restoring into an empty database with the guide's `pg_restore --clean --no-owner` exits 1 with 308 "does not exist" errors (the data loads, but the errors look like a failed restore). With `--clean --if-exists` it exits 0. The guide now uses `--if-exists`. The full drill: dump, stop the app, drop and recreate the database, restore, start. Counts matched before and after (2 programs, 2 users, 1 file), the student signed in again and the stored photo still loaded. |
| Runbook: rotate the secret key | Worked: a new `DJANGO_SECRET_KEY` in `.env` and `up -d` recreated both containers, and `web` turned healthy. |
