# Hosted demo (branch `demo`)

The `demo` branch runs a public copy of ScholarSync. Visitors sign in with the test accounts and explore. Email isn't
sent, and the data resets every night. The design is in `docs/design/2026-11-28-hosted-demo-design.md`.

Everything is free: Vercel Hobby, Neon's free tier, Cloudflare R2's free tier, and GitHub Actions on a public repo.

| Piece | Where | What it does |
|---|---|---|
| App | Vercel project, region `sin1` | `api/index.py` serves Django as one function (`vercel.json`). |
| Database | Neon project, `ap-southeast-1` | Postgres 17. The app uses the pooled URL; migrations and the reset use the direct one. |
| Files | Cloudflare R2 bucket | Uploads and downloads go through presigned URLs. The bucket stays private. |
| Deploys | `.github/workflows/demo.yml` | Each push to `demo` runs the checks, migrates, builds and deploys. |
| Nightly reset | Vercel Cron in `vercel.json` | Around 03:00 Manila time it calls `/_demo/reset/`, signed with `CRON_SECRET`. |

## One-time setup

### 1. Neon

1. Create a project in **AWS Asia Pacific (Singapore)**, `ap-southeast-1`, with Postgres 17.
2. Copy two connection strings from the dashboard's **Connect** dialog:
   - **Pooled** (the host contains `-pooler`): this is `DATABASE_URL`.
   - **Direct** (no `-pooler`): this is `DATABASE_URL_UNPOOLED`.

   Both must end in `?sslmode=require`. Production refuses a remote database without TLS.

### 2. Cloudflare R2

1. Create a bucket, for example `scholarsync-demo`. Leave it private: no public access and no custom domain.
2. **CORS policy.** Replace `<project>` with the Vercel project's name. The address has to match the site's exactly.

   ```json
   [
     {
       "AllowedOrigins": ["https://<project>.vercel.app"],
       "AllowedMethods": ["GET", "PUT", "HEAD"],
       "AllowedHeaders": ["*"],
       "ExposeHeaders": ["ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

3. **Lifecycle rule.** Delete objects with the prefix `pending/` 1 day after upload. This clears abandoned uploads.
4. **API token.** Use **Object Read & Write**, limited to this bucket. Note the access key ID, the secret access key
   and the S3 endpoint, `https://<account-id>.r2.cloudflarestorage.com`.

### 3. Vercel

1. Import the GitHub repository as a new project.
2. **Settings → Git:** turn off automatic deployments, or connect no production branch. The workflow is the only way
   to deploy.
3. **Settings → Deployment Protection:** keep Vercel Authentication on for preview deployments.
4. **Settings → Environment Variables (Production):**

   | Name | Value |
   |---|---|
   | `SCHOLARSYNC_PUBLIC_DEMO` | `true` |
   | `DJANGO_SECRET_KEY` | 50 or more random characters (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
   | `CRON_SECRET` | 32 or more random characters (the same command) |
   | `DJANGO_ALLOWED_HOSTS` | `<project>.vercel.app` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<project>.vercel.app` |
   | `SITE_URL` | `https://<project>.vercel.app` |
   | `SITE_OPERATOR_NAME` | The name the privacy and terms pages show |
   | `PRIVACY_CONTACT_EMAIL` | The address the privacy and terms pages show |
   | `DATABASE_URL` | Neon's pooled URL |
   | `DATABASE_URL_UNPOOLED` | Neon's direct URL |
   | `S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
   | `S3_PUBLIC_ENDPOINT_URL` | The same as `S3_ENDPOINT_URL` |
   | `S3_REGION` | `auto` |
   | `S3_BUCKET` | The bucket's name |
   | `S3_ACCESS_KEY_ID` | The R2 token's access key ID |
   | `S3_SECRET_ACCESS_KEY` | The R2 token's secret |
   | `S3_ADDRESSING_STYLE` | `path` |

   Leave `EMAIL_URL` unset. In the public demo, mail is printed to the function log and never sent.

   **Don't mark these variables "Sensitive".** The deploy workflow fetches them with `vercel pull` to migrate and
   build, and a Sensitive variable comes back empty. The migrate step reads only `DATABASE_URL_UNPOOLED` from the
   pulled file (`scripts/demo_env_value.py`) and masks it in the log. It fails with a message if that value is
   empty.

### 4. GitHub

1. **Settings → Environments:** create an environment named `demo`. Allow deployments from the `demo` branch only.
2. Add these secrets to the environment:

   | Secret | Where to find it |
   |---|---|
   | `VERCEL_TOKEN` | Vercel → Account Settings → Tokens (scope it to the team that owns the project) |
   | `VERCEL_ORG_ID` | `.vercel/project.json` after `npx vercel link`, or the team's Settings → General |
   | `VERCEL_PROJECT_ID` | The same file, or the project's Settings → General |

   The app's own settings stay in Vercel. The workflow fetches them with `vercel pull`.
3. Optionally, protect the `demo` branch: no force pushes, no deletion.

## Everyday work

- **Deploy:** push to `demo`. The workflow migrates Neon before the new version goes live.
- **Bring in `main`:** `git switch demo`, then `git merge main`, then push. Don't rebase `demo`. If a merge brings new
  allauth routes, `apps/demo/tests/test_lockdown.py` fails until each route is marked frozen or allowed in
  `apps/demo/lockdown.py`.
- **Reset now:** Vercel → the project → Settings → Cron Jobs → **Run**. You can also run it from a laptop with the
  production settings in the environment and the direct database URL:
  `DATABASE_URL=<direct URL> python -m uv run python manage.py reset_demo`
- **Redeploy without a change:** Vercel → Deployments → the latest production deployment → **Redeploy**.

## Limits to keep in mind

- The reset has to finish within the function's `maxDuration` (300 s in `vercel.json`). Measured times are below.
- The first request after an idle spell is slow while the function and Neon wake up.
- Hobby is for personal, non-commercial use. The demo sells nothing.

## Measurements

| Date | Where | Reset time |
|---|---|---|
| 2026-11-28 | Local Postgres + RustFS (laptop) | 11.5–15.0 s |
