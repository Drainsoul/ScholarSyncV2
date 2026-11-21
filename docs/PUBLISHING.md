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

Done 2026-11-21: the Vercel project `scholarsync-spike` and its Neon database are deleted, the local `.env.spike`,
`.vercel/` and the CLI's `.env.local` are deleted, and the spike's `.gitignore` lines and the test that guarded them
are gone. The spike never
created an R2 bucket or a Resend key.

- [ ] **The v1 Google OAuth client** leaked in the legacy repository. If it still exists in Google Cloud, delete it.
  V2 never uses it.

## 3. The repository on GitHub

The old GitHub repository is replaced by an empty one with the same name, and the local history is pushed to it. That
history keeps every commit, rewritten on 2026-11-19 so none contains private working notes (the
original is in a backup bundle outside the repository). Nothing is pushed until the maintainer decides to.

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
  README, licence or `.gitignore`, so the first push is clean.
- [ ] **Push.** The local repository has no remote until then, so an automatic fetch can't bring the old
  history back. Add it and push:

  ```
  git remote add origin https://github.com/Drainsoul/ScholarSyncV2.git
  git push -u origin main
  ```

  Check that CI is green on GitHub.
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
