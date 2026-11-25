# Publishing checklist

What the maintainer does before the repository goes public. Every step needs a person, an account or a decision.

## Before going public
- [ ] **Legal pages.** Have someone qualified read `/privacy/` and `/terms/` (`templates/core/pages/`) and the
  disclaimer in the footer (`templates/components/site_footer.html`). If they change anything, bump
  `PRIVACY_NOTICE_VERSION` in `config/settings.py` (now `2026-11-19`): signups record the version they agreed to.
- [x] **Open questions** in spec §18 (`docs/design/2026-10-11-scholarsync-design.md`): all answered, 2026-11-26.
- [x] **Barangays.** The 38 names in `apps/students/barangays.py` match the PSGC list for Taguig (2026-11-26).
- [x] **Security decisions.** `docs/security/asvs-l2.md` has no open gap (2026-11-19).
- [x] **Old Google OAuth client** deleted (2026-11-26).
- [x] **History scan.** No leaks in 547 commits (2026-11-26). Run it again right before publishing:

  ```
  docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.24.3 git /repo --redact --gitleaks-ignore-path /repo/.gitleaksignore
  ```

  It must end with "no leaks found". Accepted matches are listed with reasons in `.gitleaksignore`. If it finds a real
  secret, rotate it and remove it before pushing. (On Windows, run it from PowerShell: Git Bash rewrites `/repo`.)
- [x] **npm audit.** CI's `npm audit --audit-level=high` passes.

## GitHub settings
- [ ] Security → Dependabot alerts: enable.
- [ ] Settings → General → Danger Zone → Change visibility → **Public**.
- [ ] Security → Private vulnerability reporting: enable (`SECURITY.md` points to it; needs a public repo).
- [ ] Branches → rule for `main`: require a pull request and the CI checks, block force pushes (needs a public repo).
- [ ] Open the README's Codespaces badge once: the stack starts and a demo account signs in.

## After publishing
- [ ] Watch the first CI run and Dependabot pull requests on `main`.
- [ ] Keep `docs/HOSTING.md` as the only deployment guide. Nobody runs an official copy.
