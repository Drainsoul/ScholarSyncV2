# Security controls

The decisions and inventories that OWASP ASVS 5.0 asks to be written down (see `asvs-l2.md` for the review). Values
here are read from the code on 2026-11-18. If code and this page disagree, the code wins and this page is wrong.

## Authentication and rate limits (V6.1.1, V6.1.2)

- **Passwords:**
  - Argon2id first (`PASSWORD_HASHERS`);
  - at least 10 characters;
  - checked against the common-password list, the account's own name and email, and the site's own words (`apps/accounts/validators.py`: "scholarsync", "scholarship", "taguig", "tcu-ceaa"). Short
    program codes are only refused as that slug, so ordinary words containing them pass. No composition rules;
  - in production, refused when Have I Been Pwned's range API lists them as breached (`apps/accounts/breach.py`;
    only five hex characters of the SHA-1 leave the server; if the API is down the check is skipped and logged).
- **Two-factor sign-in:** TOTP with recovery codes (`allauth.mfa`). In production, staff and office accounts must set
  it up before any other page (`apps/accounts/mfa_policy.py`, `MFA_REQUIRED_FOR_STAFF`); students may. The office can
  remove a staff member's authenticators (a lost phone) behind its own password, which also ends that account's
  sessions.
- **Rate limits** (allauth's defaults, `ACCOUNT_RATE_LIMITS` unset; counted per client IP and per key):

  | Action | Limit |
  |---|---|
  | Sign in | 30 a minute per IP |
  | Failed sign-in | 10 a minute per IP, and 5 per 5 minutes per account |
  | Sign up | 20 a minute per IP |
  | Password reset | 20 a minute per IP, and 5 a minute per address |
  | Reset by link | 20 a minute per IP |
  | Change password | 5 a minute per user |
  | Reauthenticate | 10 a minute per user |
  | Email confirmation resend | 1 per 3 minutes per address |

  The per-account limit on failed sign-ins lasts 5 minutes and then lifts by itself. An attacker can slow an account
  down, but can't lock it out for good. Behind a proxy, `TRUSTED_PROXY_COUNT` must be right, or every visitor counts as
  the proxy (`docs/HOSTING.md` step 2).
- **Uploads:** 20 upload starts an hour for a student and 100 for staff (`apps/files/policy.py`).
- **Support messages:** 5 a day per student.

## Sessions (V7.1.1, V7.1.2, V7.1.3, V7.3.1, V7.3.2, V7.4.5, V7.5.2, V7.6.1)

- **Lifetime** (`apps/accounts/session_policy.py`):
  - sessions are stored in the database;
  - idle limit: 30 minutes for staff and the office, 60 for students (`SESSION_IDLE_MINUTES_STAFF`,
    `SESSION_IDLE_MINUTES_STUDENT`); activity is recorded at most once a minute;
  - absolute limit: 12 hours after sign-in, whatever the activity (`SESSION_COOKIE_AGE`);
  - a dialog warns 2 minutes before the idle limit ("Stay signed in" extends it) and 5 minutes before the absolute
    one (WCAG 2.2.1);
  - sign-out ends the session; deactivating an account ends all of its sessions.
- **Key rotation:** sign-in and reauthentication both issue a new session key (`apps/accounts/reauth.py`).
- **Seeing and ending sessions:**
  - everyone sees their sessions at `/accounts/sessions/` (account menu) and can sign the others out, behind the
    password; each row keeps the session's start time, IP address and browser string (`allauth.usersessions`), shown
    only to that account and removed with the session, and the privacy notice says so;
  - the office signs a staff or office account out everywhere from its account page, behind the password (audit
    `user.sessions_ended`);
  - the operator ends any account's sessions with `manage.py end_sessions --email ADDRESS` (audited by account id;
    the address is never printed or stored).
- **Concurrent sessions:** unlimited. Staff and students often use a phone and a shared office computer. A password
  change keeps only the session that made it, because Django rotates the session hash.
- **Sensitive actions** (money release and revert, accounts, memberships, tier changes): the password is asked again
  if the last confirmation is older than 5 minutes (`ACCOUNT_REAUTHENTICATION_TIMEOUT = 300`).
- **Google sign-in** (students only): Google is used once, to prove the email. It starts a local session, which then
  follows the rules above. Signing out of Google does not end it; signing out here does not sign anyone out of Google.

## Malware scanning (V5.4.3)
Optional, and the operator's choice: with `CLAMAV_HOST` set, upload confirm streams each file to clamd
(`apps/files/scanning.py`) before it is marked ready. Documents are scanned from the server-side copy; photos as sent,
before re-encoding. A hit rejects the file (reason `malware`; the signature is not recorded). An unreachable or
erroring clamd fails closed: the confirm answers 503 and the file stays pending until it can be checked. Unset, files
are not scanned; type sniffing, size checks, photo re-encoding and attachment-only downloads still apply.

## Database roles (V13.2.2)
`docs/HOSTING.md` (section 4) sets up two roles: the owner runs migrations through `DATABASE_URL_MIGRATIONS`, and the
app and worker connect as a role that can only read and write rows, with `UPDATE`, `DELETE` and `TRUNCATE` revoked on
`core_auditevent` so the audit log is append-only in the database too. The entrypoint unsets the owner's URL before the
app starts, and the image's code is root-owned, so the app can't change itself. Production refuses unencrypted
connections to other machines (database, SMTP, storage, clamd) unless `ALLOW_PLAINTEXT_SERVICES=true`
(`config/plaintext.py`; V12.3.1, V12.3.3).

## Who reads and writes what (V8.1.2)

| Data | Student (own) | Program staff and head | Scholarship office |
|---|---|---|---|
| Name, contact details, address | read, write | read (own program's applicants and scholars) | read |
| Birth date | read, write | read (applicants and scholars); never in exports | read |
| Family and household income | read, write | read (applications to their program) | read |
| Grades and education | read, write | read; staff write term records | read |
| Uploaded documents | read, upload until submitted | read (submitted or on-behalf applications) | read |
| Reports | none | read, write (own program) | read, accept or return |
| Audit log | none | head: read (own program) | read |

Forms write only the fields they show (Django forms with explicit `fields`). Staff can never edit a student's account
email or password.

## Keys and cryptography (V11.1.1, V11.1.2)

- **Keys:** each secret, where it lives, how to make it and what rotating it breaks is in `docs/HOSTING.md` (step 2,
  and the runbook's "Rotate a secret"). Secrets live only in the host's `.env` or secrets store, never in the
  repository.
- **Algorithms in use:**

  | Use | Algorithm | Key |
  |---|---|---|
  | Password hashes | Argon2id (Django's defaults) | per-password salt |
  | Sessions, CSRF, password-reset and email-confirmation links | HMAC-SHA256 (Django and allauth signing) | `DJANGO_SECRET_KEY` |
  | IP addresses in the audit log | HMAC-SHA256 | `DJANGO_SECRET_KEY` |
  | Claim links | 256-bit random token; SHA-256 of it stored | none |
  | File integrity | SHA-256 of each upload | none |
  | Presigned storage links | AWS Signature V4 (HMAC-SHA256) | the storage secret key |
  | Transport | TLS at the operator's proxy, database, storage and SMTP | the operator's certificates |

## Data classification (V14.1.1, V14.1.2, V14.2.4)

| Level | Data | Protection |
|---|---|---|
| Secret | passwords, the secret key, storage and SMTP credentials, claim and reset links | hashed or kept out of the database; never logged (`apps/core/redaction.py`); links expire |
| Sensitive personal | documents, birth dates, household income, grades | program-scoped access (`apps/core/permissions.py`); documents in a private bucket behind 5-minute links; every download audited (`file.viewed`); import files deleted after 7 days; never in logs or exports |
| Personal | names, emails, phone numbers, addresses | the same access rules; never in audit data, notifications or logs; masked in error reports |
| Internal | programs' rules, budgets, reports | staff and office only |
| Public | program pages, information pages | anyone |

## Logs (V16.1.1, V16.4.3)

| Log | What it records | Where it goes | Who reads it | Kept |
|---|---|---|---|---|
| App log | warnings and errors, JSON, with `request_id` and `user_id` on every line, emails masked and secret URLs redacted | stdout | the operator | the operator's log store |
| Access log | one line per request (gunicorn) ending in its `X-Request-ID`, secret URLs and name searches redacted | stdout | the operator | the operator's log store |
| Sentry (optional) | errors, scrubbed of bodies, cookies, query strings and personal data | Sentry | the operator | Sentry's retention |
| Audit log (`AuditEvent`) | every state change, sign-ins and file views: who, what, which record, ids only, a hashed IP | the app database, append-only | the office (all) and heads (own program) | kept with the database |

Ship stdout to a log store off the host (`docs/HOSTING.md` step 6), so logs survive the machine. Database backups
carry the audit log (step 9).
