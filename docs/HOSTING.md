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
Work on a local branch of your own, so later updates merge cleanly (see "To update later" in step 5):
```
git switch -c hosting
git rm -r apps/demo
git commit -m "chore: remove the demo for hosting"
```
That is the only code change needed. The demo holds the test accounts, the sample data and the login-page notice.
Production mode never loads it anyway, but the deploy check (step 7) fails while the folder exists, so you cannot
forget.

## 2. Create `.env`
```
cp .env.example .env
```
Edit `.env`. Set at least the values below. The app refuses to start without the secret key, the database URL, the operator name and privacy
contact, and (in production) the allowed hosts and a real SMTP `EMAIL_URL`: production refuses a blank one and the
`console://`, `memory://`, `dummy://` and `file://` backends, which would write reset and verification links to the
log or drop mail. It starts without the `S3_*` values, but then file uploads answer 503 until you set them, so set them
before real use. Production refuses the public explore storage secret from `.env.example` and `compose.yaml`: use your
own storage keys.

At least:

| Variable | Set it to |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | your own random key: `python -c "import secrets; print(secrets.token_urlsafe(64))"` or `openssl rand -base64 48` |
| `DJANGO_ALLOWED_HOSTS` | your host name, for example `scholarships.example.org` (the first entry is also used by the container health check). Empty or `*` is refused |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` plus the same host name |
| `SITE_URL` | the public address used in emailed links (claim links), for example `https://scholarships.example.org`. Must start with `https://`. Optional while the first `DJANGO_ALLOWED_HOSTS` entry is a plain host name (the default is `https://` plus that host); required when it starts with `.` |
| `SITE_OPERATOR_NAME` | your organisation's name, shown on the privacy, terms and contact pages (required) |
| `PRIVACY_CONTACT_EMAIL` | an address you read, where people send privacy requests (required) |
| `DATABASE_URL` | your PostgreSQL URL (step 4) |
| `EMAIL_URL`, `DEFAULT_FROM_EMAIL` | your SMTP server and a From address it allows (step 4). Required: production will not start without a real SMTP URL |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE` | your storage (step 4) |
| `TRUSTED_PROXY_COUNT` | the number of reverse proxies in front of the app: behind one HTTPS proxy, set `TRUSTED_PROXY_COUNT=1` (default 0). Without it, sign-in rate limits count every visitor as the proxy. `compose.production.yaml` defaults it to `1` for `web` when `.env` leaves it blank; behind two proxies (a CDN in front of yours), set `2` |
| `CSP_REPORT_ONLY` | leave `false` (enforced); `true` only to debug a blocked resource |
| `MFA_REQUIRED_FOR_STAFF` | leave `true`: staff and office accounts set up an authenticator app at their first sign-in. The office can remove a lost one from the account page |
| `PASSWORD_BREACH_CHECK` | leave `true`: new passwords are checked against Have I Been Pwned's anonymous range API (outbound HTTPS to `api.pwnedpasswords.com`; if unreachable, passwords are accepted) |
| `ALLOW_PLAINTEXT_SERVICES` | leave `false`. Production refuses `smtp://`, `http://` storage and a database URL without `sslmode=require` or `verify-full` when they point at another machine (loopback, compose service names and `host.docker.internal` are fine). Set `true` only on a private network you trust |

Also delete or replace the development-only values at the top of the file. The app refuses to start in production if
the secret key still starts with `local-dev-only-` or `explore-only-`, or if `DJANGO_KIT` is on. Production always redirects HTTP to HTTPS, so your proxy must send
`X-Forwarded-Proto: https` (step 5).

Never commit `.env`. It is git-ignored. Read and adapt the public pages before you go live: see step 2a.

The compose file forces production mode (`DJANGO_DEBUG=false`, `SCHOLARSYNC_EXPLORE=false`, `DJANGO_KIT=false`), so a
copied `.env.example` cannot switch debug, explore mode or the kit on.

## 2a. Name the operator and adapt the public pages (required)
ScholarSync is an independent portfolio project, not an official service of the City of Taguig, and you are the
operator of your copy. Before going live:
1. Set `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL` in `.env`. The app will not start in production without them.
   The privacy, terms and contact pages show them.
2. Read the privacy policy, terms of use and FAQ (`templates/core/pages/privacy.html`, `terms.html`, `help.html`,
   and `cookies.html`, `about.html`, `contact.html`). Adapt them to your organisation, your retention period (the
   privacy page asks you to state it) and your law. They are template text, not legal advice: have a qualified person
   read them.
3. If you add analytics or any optional cookie, ask visitors for consent first and update the cookie notice.

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
`?sslmode=verify-full&sslrootcert=/path/to/ca.pem` (your provider's CA certificate, mounted into both containers) when the server is on another
machine. `sslmode=require` encrypts but does not check who answers. If your URL goes through a transaction pooler such as PgBouncer, also set
`DATABASE_URL_UNPOOLED` to the direct URL; migrations use it.

**A limited role for the app (recommended).** The app needs only to read and write rows. Give it its own role, so a
flaw in the app can't change tables or rewrite the audit log, and keep the owner for migrations:
1. Connected as the database owner (the user above), create the role and the grants for every table migrations
   will create:
   ```sql
   CREATE ROLE scholarsync_app LOGIN PASSWORD 'a-long-random-password';
   GRANT CONNECT ON DATABASE dbname TO scholarsync_app;
   GRANT USAGE ON SCHEMA public TO scholarsync_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scholarsync_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO scholarsync_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scholarsync_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scholarsync_app;
   ```
2. Set `DATABASE_URL_MIGRATIONS` to the owner's URL and `DATABASE_URL` to `scholarsync_app`'s (same host and
   database). The web container migrates as the owner on every start; the app and the worker run as
   `scholarsync_app`.
3. After the first start (once the tables exist), make the audit log append-only in the database too:
   ```sql
   REVOKE UPDATE, DELETE, TRUNCATE ON core_auditevent FROM scholarsync_app;
   ```
   Later migrations never recreate that table, so this stays in place.

Check it: as `scholarsync_app`, `UPDATE core_auditevent SET action = action;` must fail with "permission denied".

**S3-compatible storage.** Create a bucket, then:
- keep it **private** (no public access); files are served through short-lived presigned links;
- set **CORS** to allow your site's origin to `PUT`, `GET` and `HEAD` from the browser, and expose the `ETag` header:
  ```json
  {"CORSRules":[{"AllowedOrigins":["https://scholarships.example.org"],"AllowedMethods":["GET","PUT","HEAD"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":3600}]}
  ```
- add a **lifecycle rule** that expires objects under the prefix `pending/` after 1 day (abandoned uploads). A
  presigned upload link stays valid for 10 minutes, so this rule is what removes abandoned or re-sent uploads;
  downloads are 5-minute links;
- create an access key limited to that bucket, and set the `S3_*` variables. The endpoint must be reachable from the
  browser as well as from the app, **over HTTPS**: browsers block uploads from an HTTPS page to a plain-HTTP address.
  Hosted providers already use HTTPS. If you run your own S3 server on the same machine, put it behind your proxy (see
  `docs/examples/Caddyfile`). Only if the browser needs a different address than the app, set
  `S3_PUBLIC_ENDPOINT_URL`.

Example, with the AWS CLI against any S3 API (the same commands the explore stack runs):
```
aws --endpoint-url "$S3_ENDPOINT_URL" s3api create-bucket --bucket YOUR_BUCKET
aws --endpoint-url "$S3_ENDPOINT_URL" s3api put-bucket-cors --bucket YOUR_BUCKET --cors-configuration file://cors.json
aws --endpoint-url "$S3_ENDPOINT_URL" s3api put-bucket-lifecycle-configuration --bucket YOUR_BUCKET --lifecycle-configuration '{"Rules":[{"ID":"expire-pending","Status":"Enabled","Filter":{"Prefix":"pending/"},"Expiration":{"Days":1}}]}'
```
Example values: Cloudflare R2 uses `S3_REGION=auto` and an endpoint like `https://ACCOUNT.r2.cloudflarestorage.com`; AWS S3
uses a region like `us-east-1`, an endpoint like `https://s3.us-east-1.amazonaws.com` (required for uploads) and
`S3_ADDRESSING_STYLE=virtual`.

**SMTP.** Take the host, port and credentials from your email provider and set one URL:
```
EMAIL_URL=submission://USER:PASSWORD@smtp.example.com:587
DEFAULT_FROM_EMAIL=ScholarSync <no-reply@your-domain.example>
```
`submission://` uses STARTTLS. For port 465 use `smtp://USER:PASSWORD@HOST:465?ssl=true`. Production refuses an
unencrypted `smtp://` URL to another machine (see `ALLOW_PLAINTEXT_SERVICES`). Set up SPF and DKIM for your sending domain with
your provider, or mail lands in spam.

**Malware scanning (optional).** Set `CLAMAV_HOST` (and `CLAMAV_PORT`, default 3310) to a clamd that accepts
`INSTREAM`, and every upload is scanned before it is accepted; a file ClamAV flags is refused with "This file can't
be accepted. Upload a different one." While the variable is set and clamd is down, uploads can't be finished
(people see "Files can't be checked right now"), so run it next to the app and watch it. For example, add to
`compose.production.yaml`:
```yaml
  clamav:
    image: clamav/clamav:1.4
    restart: unless-stopped
```
and set `CLAMAV_HOST=clamav`. clamd needs about 1.5 GB of memory for its signatures and a few minutes to load them
after it starts. Left unset (the default, and the explore stack), files are not scanned; whether to scan is your
choice.

**Google sign-in (optional, students only).** Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to offer it. If you
remove the keys later, students who signed in only with Google have no password: they must use "Forgot password" to
set one before they can sign in again.

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
loops. The proxy must also append to `X-Forwarded-For` or overwrite it (nginx:
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`; Caddy does it by default), and `TRUSTED_PROXY_COUNT`
must equal the number of proxies, or visitors can spoof their IP address and dodge the per-IP sign-in rate limits. A minimal Caddy example (an example, not a requirement):
```
scholarships.example.org {
    reverse_proxy 127.0.0.1:8000
}
```
`docs/examples/Caddyfile` adds a self-run storage server behind the same proxy.
`compose.production.yaml` publishes the port on `127.0.0.1` only, so only a proxy on the same machine can reach the app.
If the proxy runs on another host, edit the `ports` line of `web` to `"${APP_PORT:-8000}:8000"` (all interfaces) or
`"PRIVATE_IP:${APP_PORT:-8000}:8000"` (one private interface), and firewall the port so only the proxy can connect.

To update later, merge the new upstream code into your `hosting` branch, then rebuild:
```
git fetch origin
git merge origin/main
docker compose -f compose.production.yaml up -d --build
```
If upstream changed anything inside `apps/demo`, the merge stops with a modify/delete conflict there. Keep the folder
deleted and finish the merge:
```
git rm -r apps/demo
git commit --no-edit
```

**Health checks and plain HTTP.** Production redirects every plain-HTTP request to HTTPS and answers only the host names
in `DJANGO_ALLOWED_HOSTS`. That includes your platform's or load balancer's health probe: a probe that sends plain HTTP
gets a `301`, and one that sends an unknown `Host` (such as an IP address) gets a `400`. Point probes at `/healthz` with
the header `X-Forwarded-Proto: https` and an allowed `Host`, as the container's own check (`docker/healthcheck.py`)
does. The app has no switch to turn the redirect off; set the header at the proxy instead.

## 6. Background jobs
The `worker` service runs `manage.py send_outbox` (retries failed email and sends any left queued) and
`manage.py cleanup` (expired sessions, outbox rows older than 90 days, and scholar import files 7 days after upload:
they hold names and birth dates). Nothing else is needed.

If you do not run the worker, schedule the same commands yourself, for example every 5 minutes from cron or your
host's scheduler:
```
docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py send_outbox
docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py cleanup
```
Remove the `worker` service from the compose file in that case.

**Logs.** Both containers log to stdout: JSON app lines and one access line per request, with secret links and name
searches already redacted. Send them to a log store off this machine (your platform's log service, or Docker's
`journald`, `syslog` or `fluentd` logging driver), so the record survives the host. The audit log lives in the
database and is in every backup.

## 7. Run the deploy check
```
docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py check --deploy --fail-level WARNING
```
It must print `System check identified no issues`. If it says the demo app is still installed, you skipped step 1.
Then open your site over HTTPS and `/healthz`; it answers `{"ok": true}`.

## 8. First accounts and programs
Create the first scholarship-office account. It is the only way to get a first sign-in on a hosted copy. Run this
before you sign up on the site:

```
docker compose -f compose.production.yaml exec web python manage.py create_office_admin --email you@example.org --full-name "Your Name"
```

The command asks for the password twice and never prints the email address. For scripts, add `--no-input` and pass
the password in the `OFFICE_ADMIN_PASSWORD` environment variable (`exec -e OFFICE_ADMIN_PASSWORD=...`). Then sign in at
`/accounts/login/`.

If the address already signed up on the site, the command takes that account over when the address was never
verified (whoever typed it may not own it). If it was verified, the command stops; add `--promote-existing` to make
that account the office account. Either way the account gets the office role, your name and the new password; its
other email addresses, linked Google accounts, pending confirmations and sessions are removed, so whoever created it
keeps no way back in; and the change is audited.

To start with the Taguig programs, run `python manage.py seed_programs` (in the container:
`docker compose -f compose.production.yaml run --rm -e SKIP_PREPARE=1 web python manage.py seed_programs`); or create
your own programs later in the office screens. It also seeds the benefit tiers, required documents, starter schools
and academic terms. It is safe to run more than once and never overwrites your edits.

## 9. Backups
Back up the database and the bucket. Test a restore once.

- **Database:** a nightly `pg_dump`, stored somewhere other than the database server:
  ```
  pg_dump --format=custom --file=scholarsync-$(date +%F).dump "$DATABASE_URL"
  ```
  Many managed PostgreSQL services also offer point-in-time recovery; turn it on. Restore with
  `pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" FILE`, into the old database or a new empty one
  (`--if-exists` keeps an empty target from reporting hundreds of harmless "does not exist" errors).
- **Files:** enable versioning on the bucket, or copy it regularly (`aws s3 sync` or `rclone`).
- **Secrets:** keep `.env` in a password manager or secrets store. Losing `DJANGO_SECRET_KEY` signs everyone out, and
  nothing else.
- **Test a restore** (`docs/hosting-walkthrough.md` records one): dump; stop the app
  (`docker compose -f compose.production.yaml stop`); restore into the database; start it again (`start`); sign in and
  open a stored file.

## 10. Runbook
Short steps for the jobs you will repeat. All commands run in your clone, on the `hosting` branch.

**Deploy an update.**
1. Back up the database (step 9).
2. Tag the image that is running now, so you can go back: `docker tag scholarsync:production scholarsync:previous`.
3. Merge and rebuild: `git fetch origin`, `git merge origin/main`, `docker compose -f compose.production.yaml up -d --build`.
   The web container migrates on start.
4. Check: `docker compose -f compose.production.yaml ps` shows `web` healthy, the deploy check (step 7) passes, and you
   can sign in.

**Roll back.**
1. Put the previous image back and start it without building:
   `docker tag scholarsync:previous scholarsync:production`, then
   `docker compose -f compose.production.yaml up -d --no-build`.
2. Migrations are expand-only (they add, never remove or rename), so the previous code runs on the newer database.
   Restore a backup only if the update itself damaged data.
3. Reset your branch to the commit you rolled back to (`git reset --hard COMMIT`) before the next update, or the
   next build brings the bad version back.

**Restore.** Step 9. The bucket keeps its files: restore the bucket too only if files were lost.

**Rotate a secret.** Change the value in `.env`, then `docker compose -f compose.production.yaml up -d` (it recreates
both containers). What each one changes:
- `DJANGO_SECRET_KEY`: everyone is signed out, and open password-reset, set-password and email-confirmation links stop
  working (people ask for new ones). Claim links for student profiles keep working.
- `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`: create the new key at your provider first, switch `.env`, then delete
  the old key. Download links already handed out stop working when the old key goes (they last 5 minutes anyway).
- `EMAIL_URL` password: queued email is retried by the worker with the new value.
- `GOOGLE_CLIENT_SECRET`: rotate it in the Google console and here at the same time; sign-ins in progress fail once.
- The database password: change it on the server and in `DATABASE_URL` together; the app reconnects on restart.

## 11. HSTS preload
Production sends `Strict-Transport-Security: max-age=31536000; includeSubDomains` but not `preload`. Preloading puts
your domain into browsers' built-in HTTPS-only lists. It is hard to undo (removal takes months) and applies to every
subdomain. Only consider it when the whole domain, every subdomain included, will stay HTTPS for good. It needs a code
change (`SECURE_HSTS_PRELOAD = True` in `config/settings.py`) and a submission at hstspreload.org. Most copies never
need it.

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
