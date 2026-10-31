# Hosting guide

Run your own copy of ScholarSync for real: your own database, file storage and email, behind HTTPS. Nobody hosts an
official copy, and ScholarSync is an independent project, not a City of Taguig service. If you only want to look
around, use the [quick start](../README.md#quick-start) instead.

You need:
- a machine or platform that runs Docker containers, and Git;
- a domain name and a way to serve it over HTTPS (your host's TLS, or a reverse proxy such as Caddy or nginx);
- PostgreSQL 17, S3-compatible object storage, and an SMTP server (steps 4 below).

Commands are for bash. On PowerShell, set variables with `$env:NAME = "value"` and copy with `Copy-Item`.

## 1. Delete the demo
```
rm -r apps/demo
```
That is the only change needed. The demo holds the test accounts, the sample data and the login-page notice. It is
inactive in production mode anyway, but the deploy check (step 7) fails while the folder exists, so you cannot forget.

## 2. Create `.env`
```
cp .env.example .env
```
Edit `.env`. Anything marked "Required" in the file must be set. At least:

| Variable | Set it to |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | your own random key: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_ALLOWED_HOSTS` | your host name, for example `scholarships.example.org` (the first entry is also used by the container health check) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` plus the same host name |
| `DATABASE_URL` | your PostgreSQL URL (step 4) |
| `EMAIL_URL`, `DEFAULT_FROM_EMAIL` | your SMTP server and a From address it allows (step 4) |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE` | your storage (step 4) |
| `CSP_REPORT_ONLY` | leave `true` at first; set `false` once pages load with no violation reports |

Also delete or replace the development-only values at the top of the file. The app refuses to start in production if
the secret key still starts with `local-dev-only-` or `explore-only-`, or if `DJANGO_KIT` is on. Leave `DJANGO_SECURE_SSL_REDIRECT` commented out (it defaults to on); a blank
value stops the app from starting.

Never commit `.env`. It is git-ignored. Operator details (`SITE_OPERATOR_NAME`, `PRIVACY_CONTACT_EMAIL`) and the
privacy, terms and contact pages are added in a later step of this milestone; this guide will say how to set them.

The compose file forces production mode (`DJANGO_DEBUG=false`, `SCHOLARSYNC_EXPLORE=false`, `DJANGO_KIT=false`), so a
copied `.env.example` cannot switch debug, explore mode or the kit on.

## 3. Rebrand (optional)
The "City of Taguig" label and the logo are fixed in the code, so a copy for another organisation is a small edit:
- the name, brand block and footer text in `templates/layouts/` (`public.html`, `auth.html`, `app.html`; search for
  `City of Taguig`);
- the logo mark (the `logo` icon in `templates/components/`) and the favicon `static/images/favicon.svg`;
- the colours and fonts in `frontend/src/styles/`.

You are the operator of your copy: say so to your users, and do not present it as a City of Taguig service unless it
is one.

## 4. Provision PostgreSQL, storage and email
Use any provider. Names below are examples only.

**PostgreSQL 17.** Create an empty database and a user that owns it. Set
`DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME` (URL-encode special characters in the password). Add
`?sslmode=require` if the server needs TLS. If your URL goes through a transaction pooler such as PgBouncer, also set
`DATABASE_URL_UNPOOLED` to the direct URL; migrations use it.

**S3-compatible storage.** Create a bucket, then:
- keep it **private** (no public access); files are served through short-lived presigned links;
- set **CORS** to allow your site's origin to `PUT`, `GET` and `HEAD` from the browser, and expose the `ETag` header:
  ```json
  {"CORSRules":[{"AllowedOrigins":["https://scholarships.example.org"],"AllowedMethods":["GET","PUT","HEAD"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":3600}]}
  ```
- add a **lifecycle rule** that expires objects under the prefix `pending/` after 1 day (abandoned uploads);
- create an access key limited to that bucket, and set the `S3_*` variables. The endpoint must be reachable from the
  browser as well as from the app. Only if the browser needs a different address than the app, set
  `S3_PUBLIC_ENDPOINT_URL`.

Example, with the AWS CLI against any S3 API (the same commands the explore stack runs):
```
aws --endpoint-url "$S3_ENDPOINT_URL" s3api create-bucket --bucket YOUR_BUCKET
aws --endpoint-url "$S3_ENDPOINT_URL" s3api put-bucket-cors --bucket YOUR_BUCKET --cors-configuration file://cors.json
aws --endpoint-url "$S3_ENDPOINT_URL" s3api put-bucket-lifecycle-configuration --bucket YOUR_BUCKET --lifecycle-configuration '{"Rules":[{"ID":"expire-pending","Status":"Enabled","Filter":{"Prefix":"pending/"},"Expiration":{"Days":1}}]}'
```
Example values: Cloudflare R2 uses `S3_REGION=auto` and an endpoint like `https://ACCOUNT.r2.cloudflarestorage.com`; AWS S3
uses a region like `us-east-1` and `S3_ADDRESSING_STYLE=virtual`.

**SMTP.** Take the host, port and credentials from your email provider and set one URL:
```
EMAIL_URL=smtp+tls://USER:PASSWORD@smtp.example.com:587
DEFAULT_FROM_EMAIL=ScholarSync <no-reply@your-domain.example>
```
Use `smtps://` for port 465 and `smtp://` for an unencrypted relay. Set up SPF and DKIM for your sending domain with
your provider, or mail lands in spam.

## 5. Build and run behind HTTPS
```
docker compose -f compose.production.yaml up -d --build
```
This builds the image from source (nothing is published to a registry) and starts `web` (gunicorn on port 8000) and
`worker`. The web container migrates the database on every start. Check it:
```
docker compose -f compose.production.yaml ps
docker compose -f compose.production.yaml logs web
```

Put a TLS reverse proxy in front of the app and forward to `APP_PORT` (default 8000). The proxy must send
`X-Forwarded-Proto: https` and the original `Host`. The app redirects plain HTTP to HTTPS, so without that header it
loops. A minimal Caddy example (an example, not a requirement):
```
scholarships.example.org {
    reverse_proxy 127.0.0.1:8000
}
```
By default `compose.production.yaml` publishes the port on all interfaces. If the proxy runs on the same machine, edit
the `ports` line to `"127.0.0.1:${APP_PORT:-8000}:8000"` so only the proxy can reach the app.

To update later: `git pull`, then run the same `up -d --build` command.

## 6. Background jobs
The `worker` service runs `manage.py cleanup` every 5 minutes (it deletes expired sessions now, and will also retry
failed email and clear old rows as features arrive). Nothing else is needed.

If you do not run the worker, schedule the same command yourself, for example every 5 minutes from cron or your
host's scheduler:
```
docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py cleanup
```
Remove the `worker` service from the compose file in that case.

## 7. Run the deploy check
```
docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py check --deploy --fail-level WARNING
```
It must print `System check identified no issues`. If it says the demo app is still installed, you skipped step 1.
Then open your site over HTTPS and `/healthz`; it answers `{"ok": true}`.

## 8. First accounts and programs
Sign-in and the scholarship-office account arrive with M4. This section will give the command that creates the first
scholarship-office account, and the optional `seed_programs` command that loads the TCU CEAA and LANI starter programs,
the school list and the terms. Until then a hosted copy has no way to sign in.

## 9. Backups
Back up the database and the bucket. Test a restore once.

- **Database:** a nightly `pg_dump`, stored somewhere other than the database server:
  ```
  pg_dump --format=custom --file=scholarsync-$(date +%F).dump "$DATABASE_URL"
  ```
  Many managed PostgreSQL services also offer point-in-time recovery; turn it on. Restore with
  `pg_restore --clean --no-owner --dbname "$DATABASE_URL" FILE`.
- **Files:** enable versioning on the bucket, or copy it regularly (`aws s3 sync` or `rclone`).
- **Secrets:** keep `.env` in a password manager or secrets store. Losing `DJANGO_SECRET_KEY` signs everyone out, and
  nothing else.

## Troubleshooting
- **The app exits at start with `ImproperlyConfigured`:** the message names the variable. Fix `.env` and run `up -d`
  again.
- **Redirect loop, or "Bad Request (400)":** the proxy does not send `X-Forwarded-Proto: https`, or the `Host` is not in
  `DJANGO_ALLOWED_HOSTS`.
- **"CSRF verification failed" when signing in:** `DJANGO_CSRF_TRUSTED_ORIGINS` must hold `https://your-host`.
- **Uploads fail in the browser:** check the bucket's CORS origin and that the storage endpoint is reachable from the
  browser. Browser console errors name the blocked origin.
- **`web` stays "unhealthy":** `docker compose -f compose.production.yaml logs web`. The health check sends your first
  allowed host with `X-Forwarded-Proto: https`, so a wrong `DJANGO_ALLOWED_HOSTS` shows up there.
