# Issues and pull requests

How to title, write and link issues and pull requests in this repository. GitHub's issue forms and the pull request
template follow this guide.

## Titles

| Kind | Title | Example |
|---|---|---|
| Bug | `[BUG] ISS#<n>: <what goes wrong>` | `[BUG] ISS#2: Saving two templates with one title at once gives a 500` |
| Feature | `[FEATURE] ISS#<n>: <what it adds>` | `[FEATURE] ISS#7: Export the support inbox as CSV` |
| Task (docs, chores, refactors) | `[TASK] ISS#<n>: <what it does>` | `[TASK] ISS#8: Document the reply template placeholders` |
| Epic (groups other issues) | `[EPIC] ISS#<n>: <the goal>` | `[EPIC] ISS#1: Bug-fix pass on support replies` |
| Pull request | `PR#<n>: <Conventional Commit subject>` | `PR#2: fix: refuse a duplicate template title instead of a 500` |

### Numbers
- `ISS#` and `PR#` are **this project's own counters**. Each starts at 1 and goes up by one. They are not GitHub's
  `#` numbers: GitHub numbers issues and pull requests in one shared sequence, so `ISS#2` might be GitHub's `#9`.
- To find the next number, look up the highest one in use and add one:
  ```
  gh issue list --state all --search "ISS# in:title" --limit 5
  gh pr list --state all --search "PR# in:title" --limit 5
  ```
  On the website, search `ISS# in:title` in Issues or `PR# in:title` in Pull requests. If two people take the same
  number, the later one renames.
- Dependabot pull requests keep their own titles and are exempt from this format.

## Linking
- **Every pull request names the issue it fixes, or `none`.** Write the link with GitHub's number, so it links and
  closes the issue on merge, followed by the project number: `Fixes #9 (ISS#2)`. `Fixes ISS#2` alone links to
  nothing.
- One pull request fixes one issue where possible. A pull request that fixes several lists each on its own line.
- An epic lists its issues as a task list with GitHub numbers (`- [ ] #9 ISS#2: …`), so GitHub ticks them as they
  close.

## Keep it public and self-contained
Issues and pull requests are public. Everything they say must be checkable from the repository itself:
- point at tracked files (`apps/workspace/reply_templates.py:47`), spec sections
  (`docs/design/2026-10-11-scholarsync-v2-design.md` §4.8) and tests;
- describe what happens with the demo accounts or factory data, never real people;
- never include personal data (names, email addresses, phone numbers, student records), secrets, tokens, `.env`
  values, local file paths, screenshots of real data, or links to private documents and chats.

Security problems don't go in issues at all: follow [SECURITY.md](../SECURITY.md).

## Before you open a pull request
- The checks in [CONTRIBUTING.md](../CONTRIBUTING.md#commands) pass locally.
- A bug fix comes with a test that fails without it.
- A change to the design or architecture updates the spec in the same pull request.
- Commits follow Conventional Commits and touch only what the change needs.
