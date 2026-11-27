# Hosted demo on Vercel: design

- **Date:** 2026-11-28
- **Status:** draft, awaiting the maintainer's approval
- **Branch:** `demo` (long-lived; never merged into `main`)
- **Builds on:** `2026-10-11-scholarsync-design.md` (rev 41) and `2026-10-30-open-source-self-hosting-design.md`

## 1. Intent

People who want to look at ScholarSync currently have to run `docker compose up` (or open a codespace). The
maintainer wants a public copy that anyone can open in a browser and explore with the developer test accounts,
without installing anything. It is a portfolio showcase, not a service: there is no real data, no real users and
no email.

## 2. Goals, non-goals, anti-goals

**Goals**
- A public HTTPS URL (`<project>.vercel.app`) that serves the full app with the demo's test accounts and sample
  data for both programs, the same as explore mode shows on localhost.
- Free to run: Vercel Hobby, Neon free tier, Cloudflare R2 free tier, GitHub Actions on the public repo.
- Every night the database and uploaded files go back to the clean demo state, so one visitor's changes don't
  ruin the copy for the next.
- The demo accounts can't be taken over: visitors can't change their password, email address or 2FA, and
  can't lock other visitors out.
- `main` and the self-hosting story are unchanged. Everything Vercel-specific lives on the `demo` branch.

**Non-goals**
- Email of any kind (signup, password reset, verification, notifications, support replies by email).
- New user accounts. Sign-up and Google sign-in are off; visitors use the test accounts only.
- A background worker. Nothing needs sending, and the nightly job does the cleanup.
- Uptime promises, monitoring or a custom domain.

**Anti-goals (failure even if it technically works)**
- Production's security posture gets weaker on `main`, or a self-hoster could switch on the public-demo mode by
  accident and serve the shared demo password on a real copy.
- A visitor changes a demo password or email and everyone else is locked out until the next reset.
- The demo becomes a free file host: uploads are kept indefinitely or can be shared outside the app.
- Visitors mistake it for the City of Taguig's real platform, or enter real personal data.

## 3. Current state (what this changes)

- `config/settings.py` has three modes. Explore mode (`SCHOLARSYNC_EXPLORE`) serves `localhost` and `127.0.0.1`
  only, over HTTP. Production mode (neither flag) forces HTTPS, HSTS, real hosts, real SMTP and real secrets, and
  turns the demo off (`DEMO_ACTIVE = DEMO_INSTALLED and not PRODUCTION`). No current mode fits a public demo.
- `apps/demo/` holds the accounts (one published password, `explore-demo-2026`), the idempotent `load_demo`
  loader (it only adds what is missing and resets nothing), and the login notice that lists the accounts.
  Core's deploy check `demo.E001` fails while the folder exists.
- The M1 spike (2026-10, historical) ran a minimal page on Vercel + Neon + R2. Its `vercel.json`, build script and
  host detection were removed in M3.5 and are no longer in the tree. The spike branch no longer exists.
- Uploads go straight from the browser to S3-compatible storage through presigned PUT URLs. Downloads are
  presigned attachments. Static files are served by WhiteNoise (`CompressedManifestStaticFilesStorage`) from a
  Vite build. The cache is Django's database cache.

## 4. Approaches considered

| Approach | Trade-offs | Verdict |
|---|---|---|
| **Vercel Hobby + Neon + Cloudflare R2** | Free. Uses the presigned-upload code as it is (R2 speaks S3). Cold starts after idle. No long-running processes, so no worker. Function time and bundle size limits. R2 needs a card on file. | **Chosen** by the maintainer (free). |
| Small VPS running `docker compose` + Caddy | Reuses everything, including RustFS, Postgres and the worker. No platform limits. About $5 a month. | Rejected: costs money. |
| Render / Koyeb free tier | Free, but the app sleeps, Render's free Postgres expires after 30 days, and storage still needs R2. | Rejected: breaks more often for the same setup work. |

## 5. Design

### 5.1 A fourth mode: public demo

Add the setting `SCHOLARSYNC_PUBLIC_DEMO` (default false), read in `config/settings.py` **on the `demo` branch
only**.

- It is **production security with the demo switched on**. Everything that production enforces stays enforced:
  HTTPS redirect, HSTS, secure cookies, a real `DJANGO_ALLOWED_HOSTS` (no `*`, no explore hosts), a real secret
  key (not the `explore-only-` one), a real storage secret, an enforced CSP, and `DEBUG` off.
- What changes from production:
  - `DEMO_ACTIVE` is true, so `apps.demo` is installed and the login notice shows the accounts.
  - Email: `EMAIL_URL` may be blank. It then falls back to Django's console backend, so mail is printed to the
    function log and never sent. The production check that refuses undelivered backends is skipped in this mode.
  - `PRIVACY_CONTACT_EMAIL` is still required (the privacy and terms pages name the operator). The maintainer
    picks the address and sets it in Vercel.
  - `demo.E001` (the "delete `apps/demo`" deploy check) is skipped in this mode.
  - `MFA_REQUIRED_FOR_STAFF` is false (designer's call). Production sends every staff and office account
    without TOTP to `mfa_activate_totp`. The demo accounts have no authenticators, and §5.2 freezes 2FA, so the
    staff and office demo accounts would otherwise be stuck on a blocked page. Publishing a shared TOTP secret was
    rejected because it adds loader and notice work and protects nothing.
  - The kit at `/_kit/` stays off (the production default).
- It can't be combined with `DJANGO_DEBUG` or `SCHOLARSYNC_EXPLORE`. Settings raise `ImproperlyConfigured` if
  it is.
- Because the flag only exists on the `demo` branch, a self-hoster running `main` can't switch it on. This
  keeps the anti-goal in §2.

### 5.2 Locking down the demo

In public-demo mode only:

- **Closed sign-up.** The allauth account adapter's `is_open_for_signup` returns false. The sign-up link and page
  say "This demo uses test accounts only" and point to the login notice. Google sign-in is off: no
  `GOOGLE_CLIENT_ID` is set, and the social adapter also refuses sign-up.
- **Frozen account security.** Visitors can't change passwords, set passwords, reset passwords, change or add
  email addresses, or add, remove or change 2FA (TOTP, recovery codes, WebAuthn, if enabled). Those routes
  return a page that says the demo accounts can't be changed. Blocking them by URL name in one middleware or
  adapter hook is the simplest way, and a test lists every allauth route so new ones can't slip through.
- **Staff screens that manage people stay usable.** For example, the office can create a staff account: the
  invite email goes to the console, and the nightly reset removes the account. The builder checks every screen
  that sets a password or email on **another** user. Where one could lock a demo account (say, the office
  changing a demo staff member's email), it is blocked the same way, but only for the accounts listed in
  `apps/demo/accounts.py`.
- **Lockout.** Login rate limits stay as they are. Someone hammering a demo account then locks it only briefly,
  and the reset clears it anyway.
- **Visible banner.** Every page shows a slim, non-dismissible banner: "Public demo. Data resets every night at
  03:00 Manila time. Don't enter real personal information or upload real documents." It's a component in
  `templates/components/`, styled with tokens, WCAG AA, with no inline CSS or JS.
- **Uploads.** The existing type and size checks stay. The R2 bucket has a lifecycle rule that expires
  `pending/` after 1 day, as `compose.yaml` does. The nightly reset empties the bucket (§5.4).

### 5.3 Hosting on Vercel

- **Runtime:** Vercel's Python runtime serves the WSGI app (`config/wsgi.py`) as one function. Region: `sin1`
  (Singapore), the closest to Taguig and to Neon's `ap-southeast-1`.
- **Build:** the Vercel build installs the Python dependencies from `uv.lock` (no dev group), builds the Vite
  bundle (`npm ci` + `npm run build` inside `frontend/`), and runs `collectstatic`. Static files are served by
  WhiteNoise from the function, or by Vercel's CDN if that turns out simpler. That is the builder's call
  (§7), as long as hashed names, compression and the CSP keep working.
- **Configuration:** a `vercel.json` (region, function memory and duration, build command, routes) and any small
  entry module Vercel needs, both on the `demo` branch only.
- **Environment (Vercel project settings, never in git):** `SCHOLARSYNC_PUBLIC_DEMO=true`, `DJANGO_SECRET_KEY`,
  `DJANGO_ALLOWED_HOSTS=<project>.vercel.app`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<project>.vercel.app`,
  `SITE_URL`, `DATABASE_URL` (Neon pooled), `S3_*` for R2 (`S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL`,
  `S3_REGION=auto`, bucket, keys, addressing style), `PRIVACY_CONTACT_EMAIL`. `.env.example` on the `demo` branch
  documents them.
- **Database:** Neon free tier, one project in `ap-southeast-1`. The app uses the pooled connection string, and
  migrations and the reset use the direct one (`DATABASE_URL_UNPOOLED`), as `docker/entrypoint.sh` already
  expects. `conn_max_age=0` stays.
- **Storage:** one R2 bucket with a CORS rule that allows `PUT`, `GET` and `HEAD` from
  `https://<project>.vercel.app` only, plus the `pending/` lifecycle rule. The bucket stays private: every read
  is a presigned URL.
- **Preview deployments:** off, or protected by Vercel authentication. Only the `demo` branch deploys, and only to
  production.

### 5.4 Deploy and nightly reset: one GitHub Actions workflow

One workflow on the `demo` branch (`.github/workflows/demo.yml`) does all of the database and deploy work.
GitHub Actions is free on a public repo and has no Vercel function time limit, so `load_demo`'s run time
doesn't matter.

- **On push to `demo`:** run the checks that matter for this branch (ruff, mypy, pytest), then
  `migrate` + `createcachetable` against Neon's direct URL, then `vercel deploy --prod` with the Vercel CLI.
  Migrations run before the new code goes live. Vercel's own Git auto-deploy is turned off, so the workflow is
  the only way to deploy.
- **Nightly at 03:00 Asia/Manila (19:00 UTC):** run a new management command `reset_demo` against Neon's direct
  URL. It:
  1. refuses to run unless `DEMO_ACTIVE` is true and `SCHOLARSYNC_PUBLIC_DEMO` is set (it never runs on a real
     copy);
  2. empties the R2 bucket (every key, including `pending/`);
  3. empties every app table (`flush`, or a truncate in one transaction), keeping the schema and migrations;
  4. runs `load_demo`, which recreates the accounts, the samples and their sample files in R2;
  5. clears the database cache table and Django sessions, so every visitor is signed out.
- **Manual trigger** (`workflow_dispatch`) for both jobs, so the maintainer can reset or redeploy on demand.
- **Secrets** (GitHub repo secrets, available only to this workflow): `VERCEL_TOKEN`, `VERCEL_ORG_ID`,
  `VERCEL_PROJECT_ID`, `DEMO_DATABASE_URL_UNPOOLED`, the R2 keys, `DEMO_SECRET_KEY`.
- The workflow uses the same pinned action versions as `ci.yml`.

### 5.5 Keeping the branch current

`demo` = `main` + the commits in this design. When `main` moves, the maintainer merges `main` into `demo` (no
rebase, so the history stays readable). The push redeploys. `main`'s branch rule is untouched. `demo` gets a
lighter rule: no force push and no deletion.

### 5.6 What stays out of `main`

Everything in this document. `main`'s README may later link to the live demo, but that link goes through the
normal issue and PR flow on `main`, as its own decision.

## 6. Testing

- Settings tests for the new mode: it needs real hosts, a real secret and a real storage secret; it refuses
  `DEBUG` or explore; it allows a blank `EMAIL_URL`; it turns the demo on.
- Lockdown tests: every allauth route that changes credentials, email or 2FA is refused in this mode, and works
  outside it. Sign-up is closed. Every page shows the banner.
- `reset_demo` tests (moto for S3): it refuses outside the mode, empties the bucket and tables, and leaves a
  database where every demo account can sign in.
- The existing suite still passes on `demo`.
- After the first deploy, a manual smoke test on the live URL: sign in as one account from each group, upload
  and download a document, run the reset workflow, and confirm the upload is gone.

## 7. Left to the builder

- Exactly how the WSGI app is wired into Vercel's Python runtime (entry module, `vercel.json` shape, how `uv.lock`
  becomes the installed environment), and whether static files come from WhiteNoise in the function or the CDN.
- Whether `reset_demo` uses `flush` or an explicit truncate. Either is fine if it keeps the migrations table and
  finishes in one go.
- Where the credential-route lockdown hooks in (middleware, URL overrides or allauth adapter methods), as long as
  the route-list test covers it.
- Banner wording and placement within the layouts, following the design tokens.
- Function memory and duration settings within Hobby's limits.

## 8. Risks

- **Bundle size.** The full dependency set (boto3, Pillow, cryptography, openpyxl, allauth) has to fit Vercel's
  Python function size limit. Check this first. If it doesn't fit, stop and come back to the maintainer before
  trimming anything.
- **Cold starts.** The first request after an idle spell waits for the function and for Neon to wake. That's
  acceptable for a demo.
- **Hobby is non-commercial.** A personal portfolio demo is within the terms. Nothing on the demo may sell
  anything.
- **Abuse of uploads.** Mitigated by the type and size checks, the private bucket, presigned-only access, the
  banner and the nightly purge. If abuse shows up, the fallback is turning uploads off in this mode.
