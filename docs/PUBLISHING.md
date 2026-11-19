# Publishing checklist

What the maintainer does, in order, before the repository goes public. Each step says how to check it is done.
Nothing here is automated: every step needs a person, an account or a decision.

## 1. Content only a person can confirm

- [ ] **Legal pages.** Have someone qualified read `/privacy/` and `/terms/` (`templates/core/pages/`) and the
  not-affiliated disclaimer in the footer (`templates/components/site_footer.html`). The privacy notice is version `2026-11-19` (`PRIVACY_NOTICE_VERSION` in
  `config/settings.py`); bump it if they change anything, because signups record the version they agreed to.
- [ ] **Open questions.** Answer or close the questions in spec §18
  (`docs/design/2026-10-11-scholarsync-v2-design.md`), and renumber them if any are removed.
- [ ] **Barangays.** Check the 38 names in `apps/students/barangays.py` against the PSGC list for Taguig, and fix any
  spelling.
- [x] **Security decisions.** Done 2026-11-19: V6.5.2 fixed (2FA secrets encrypted at rest) and V14.2.1 (names in
  search URLs) accepted; `docs/security/asvs-l2.md` has no open gap.

## 2. Remove the M1 spike

The Vercel spike (`scholarsync-spike`) is unused since spec revision 5. Its tokens are in the local, git-ignored
`.env.spike`.

- [ ] **Vercel project.** `vercel project rm scholarsync-spike` (or Vercel → the project → Settings → Delete).
- [ ] **Neon database** (added through the Vercel Marketplace). Vercel → Storage → the Neon database → Settings →
  Delete; then check the Neon console shows no project left.
- [ ] **Cloudflare R2.** Delete the spike bucket (`npx wrangler r2 bucket delete BUCKET_NAME`, or the R2 dashboard)
  and revoke its API token (R2 → Manage API tokens).
- [ ] **Resend.** Revoke the API key (Resend → API Keys).
- [ ] **Local leftovers.** Delete `.env.spike` and `.vercel/`, remove their two lines from `.gitignore` (under "M1
  spike leftovers"), and delete `test_spike_leftovers_stay_git_ignored` in `tests/test_no_vercel.py`. Commit that
  as `chore: remove the M1 spike leftovers`.
- [ ] **The v1 Google OAuth client** leaked in the legacy repository. If it still exists in Google Cloud, delete it.
  V2 never uses it.

## 3. The repository on GitHub

The repository is published with a fresh history: the local `main` holds a single new commit, and the old GitHub
repository is replaced by an empty one with the same name. Nothing is pushed until the maintainer decides to.

- [ ] **History scan.** Run gitleaks on the local repository right before publishing:

  ```
  docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.24.3 git /repo --redact --gitleaks-ignore-path /repo/.gitleaksignore
  ```

  It must end with "no leaks found". Every accepted match (placeholders, test passwords, the public demo password,
  false positives) is listed with its reason in `.gitleaksignore`. If it finds a real secret, rotate the secret and
  remove it before the commit is pushed.
- [ ] **npm audit.** CI's `npm audit` reports picomatch ≤ 4.0.7, which comes in through Vite's build tooling and is
  never shipped to browsers. Either wait for a patched release, or audit runtime dependencies only
  (`npm audit --omit=dev` in `.github/workflows/`).
- [ ] **Replace the GitHub repository.** Delete `Drainsoul/ScholarSyncV2` (GitHub → the repository → Settings →
  General → Danger Zone → Delete this repository), then create a new, empty repository with the same name. Add no
  README, licence or `.gitignore`, so the first push is clean. The local `origin` remote keeps the same URL.
- [ ] **Push.** `git push -u origin main`. Check that CI is green on GitHub.
- [ ] **Settings** (GitHub → the repository → Settings):
  - Security → Private vulnerability reporting: enable (`SECURITY.md` points to it);
  - Security → Dependabot alerts: enable (`.github/dependabot.yml` already proposes updates);
  - Branches → add a rule for `main`: require a pull request and the CI checks, and block force pushes.
- [ ] **Make it public.** GitHub → Settings → General → Danger Zone → Change visibility → Public.
- [ ] **Codespaces.** Open the README's Codespaces badge once, and check the explore stack starts and the demo
  accounts sign in.

## 4. After publishing

- [ ] Watch the first Dependabot pull requests and the first CI run on `main`.
- [ ] Keep `docs/HOSTING.md` as the only deployment guide. Nobody runs an official copy.
