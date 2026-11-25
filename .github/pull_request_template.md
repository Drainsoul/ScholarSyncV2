<!--
Title: PR#<n>: <Conventional Commit subject>, e.g. "PR#2: fix: refuse a duplicate template title instead of a 500".
PR# is this project's own counter (see .github/ISSUES_AND_PULL_REQUESTS.md), not GitHub's number.
Everything here is public: no personal data, secrets, local paths or links to private documents.
-->

## Issue
<!-- Required. GitHub's number then the project number, e.g. "Fixes #9 (ISS#2)". Write "none" if there is none. -->
Fixes #

## What changed
<!-- What was wrong or missing, and what this does about it. Point at files and spec sections. -->

## How it was tested
<!-- The tests added or changed, and anything checked by hand with the demo accounts. -->

## Checklist
- [ ] The checks in CONTRIBUTING.md pass (ruff, format, mypy, migrations check, pytest; e2e and npm checks if the
      front end changed)
- [ ] A bug fix has a test that fails without it
- [ ] The spec is updated if the design or behaviour it describes changed
- [ ] No secrets, personal data, local paths or private links in the code, commits or this description
