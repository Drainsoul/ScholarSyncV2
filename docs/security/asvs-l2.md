# OWASP ASVS 5.0 Level 2 review

This review checks ScholarSync against every Level 1 and Level 2 requirement of the OWASP Application Security Verification Standard 5.0.0, taken from OWASP's `v5.0.0` tag (`5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.flat.json`). It was done on 2026-11-18 against this repository's code and its default configuration. Each host's infrastructure (TLS termination, the database, the bucket, the mail server) belongs to its operator, and `docs/HOSTING.md` tells them what to set. The statuses mean:

- **Met:** the code, configuration or tests at HEAD satisfy the requirement; the evidence names where.
- **Not applicable:** the requirement doesn't apply, because the app has no such feature or it falls wholly on the operator's infrastructure.
- **Gap:** the requirement applies and isn't fully met. Every gap is listed under [Open gaps](#open-gaps) with a suggested fix.

Evidence is a repo-relative path with a line number, a test node id, or both. Where it names a Django or library default, it names the setting or mechanism.

**Summary:** 253 requirements: 185 Met, 67 Not applicable, 1 Gap accepted (after the M13 follow-ups and the V6.5.2 fix; M12 left 14 gaps, and the first pass found 42).

## V1 Encoding and Sanitization

16 Met, 11 Not applicable, 0 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V1.1.1 | L2 | Decode input to canonical form once, before processing. | Met | Django decodes the URL, query and form body once per request; no app code unquotes or base64-decodes request data. |
| V1.1.2 | L2 | Encode output as the last step, or by the interpreter itself. | Met | Django template autoescaping at render (`config/settings.py:192`); `format_html` in `apps/core/templatetags/ui.py:59`; JSON by `JsonResponse`. |
| V1.2.1 | L1 | Output encoding fits the context (HTML, attributes, CSS, headers). | Met | Autoescape on everywhere; no `\|safe` on user data (only `mark_safe` is `apps/core/templatetags/slots.py:19` on a rendered template); `apps/core/tests/test_templates.py::test_templates_have_no_inline_script_or_style`. |
| V1.2.2 | L1 | Dynamic URLs encode untrusted data; only safe URL protocols allowed. | Met | URLs come from `reverse()`; the queue filter is re-encoded from allowed keys (`apps/applications/staff_views.py:55`); no user-entered URL is ever rendered as a link (no `URLField`); `tests/test_rendered_pages.py::test_every_get_page_is_csp_clean` rejects `javascript:` URLs. |
| V1.2.3 | L1 | Encode when building JavaScript or JSON content. | Met | `JsonResponse` and django-htmx `trigger_client_event` serialise JSON (`apps/core/htmx.py:26`); no inline scripts (`templates/base.html:20` only puts the alphanumeric CSRF token in `hx-headers`). |
| V1.2.4 | L1 | Database queries are parameterised or use an ORM. | Met | Django ORM; the only raw SQL is the constant `SELECT 1` (`apps/core/views.py:22`) and a parameterised advisory lock (`apps/programs/services.py:119`). |
| V1.2.5 | L1 | Protect against OS command injection. | Met | No `subprocess`, `os.system` or shell call anywhere under `apps/` or `config/`. |
| V1.2.6 | L2 | Protect against LDAP injection. | Not applicable | No LDAP. |
| V1.2.7 | L2 | Protect against XPath injection. | Not applicable | No XPath queries. |
| V1.2.8 | L2 | Configure LaTeX processors securely. | Not applicable | No LaTeX. |
| V1.2.9 | L2 | Escape special characters in regular expressions built from input. | Not applicable | No regex is built from user input; patterns are constants (`apps/core/redaction.py:15`) and there are no `__regex` lookups. |
| V1.3.1 | L1 | Sanitise WYSIWYG or rich HTML input with a known library. | Not applicable | No rich-text input; every text field is plain text, autoescaped on output. |
| V1.3.2 | L1 | Avoid eval and dynamic code execution. | Met | No `eval`/`new Function` in `frontend/src/`; htmx `allowEval:false` and `allowScriptTags:false` (`templates/base.html:8`); CSP has no `unsafe-eval` (`config/settings.py:460`). |
| V1.3.3 | L2 | Sanitise data for dangerous contexts; limit characters and length. | Met | Spreadsheet formula prefixes neutralised (`apps/awards/tabular.py:178`; `apps/awards/tests/test_exporting.py::test_formula_name_neutralised_csv_and_xlsx`); file names cleaned (`apps/files/names.py:14`). |
| V1.3.4 | L2 | Validate or sanitise user-supplied SVG. | Met | SVG is never accepted: each purpose allows only PDF, JPEG, PNG, CSV or XLSX (`apps/files/policy.py:55`). |
| V1.3.5 | L2 | Sanitise or disable user-supplied Markdown, CSS, XSL or templates. | Not applicable | Users cannot supply Markdown, stylesheets or templates. |
| V1.3.6 | L2 | Protect against SSRF with allowlisted protocols, hosts and ports. | Not applicable | The backend never fetches a URL a user supplies; outbound calls go only to configured storage, SMTP and Google endpoints. |
| V1.3.7 | L2 | Never build templates from untrusted input. | Met | Templates are files; `include_if_present` only takes a constant name (`templates/account/login.html:6`); no `Template(...)` from strings. |
| V1.3.8 | L2 | Sanitise input to JNDI queries. | Not applicable | No JNDI (Python). |
| V1.3.9 | L2 | Sanitise content sent to memcache. | Not applicable | No memcache; the database cache holds only allauth rate-limit counters (`config/settings.py:287`). |
| V1.3.10 | L2 | Sanitise format strings that could resolve unexpectedly. | Met | Format templates are constants and user data only goes in as arguments (`apps/files/services.py:72`, `apps/awards/tabular.py:32`). |
| V1.3.11 | L2 | Sanitise input passed to mail systems (SMTP/IMAP injection). | Met | Mail goes through `EmailMultiAlternatives` (`apps/workspace/emails.py:170`), whose header encoding refuses newlines; recipients are validated email addresses. |
| V1.4.1 | L2 | Use memory-safe strings and copies to prevent overflows. | Not applicable | Python; the project has no native code of its own. |
| V1.4.2 | L2 | Prevent integer overflows with sign, range and input checks. | Met | Python integers do not overflow; values stored in bounded columns are range-checked first (upload size `apps/files/services.py:85`, money in `DecimalField(12, 2)` forms). |
| V1.4.3 | L2 | Release memory and clear dangling pointers. | Not applicable | Python is garbage-collected; no manual memory management. |
| V1.5.1 | L1 | XML parsers are restrictive; external entities disabled (XXE). | Met | `defusedxml` is a dependency (`pyproject.toml:26`), which openpyxl uses automatically for XLSX imports (`apps/awards/tabular.py:142`). |
| V1.5.2 | L2 | Deserialisation of untrusted data uses allowlisted types. | Met | Only JSON is parsed from clients (`apps/files/views.py:50`); sessions use Django's default JSON serializer; nothing uses `pickle`. |

## V2 Validation and Business Logic

11 Met, 0 Not applicable, 0 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V2.1.1 | L1 | Documentation defines input validation rules for data items. | Met | `docs/design/2026-10-11-scholarsync-design.md` §4 (domain model, line 151) and §7 upload purposes (line 665). |
| V2.1.2 | L2 | Documentation defines checks for consistency of combined data items. | Met | `docs/design/2026-10-11-scholarsync-design.md` §8 eligibility rules (scale-aware GWA, window, schools; line 716). |
| V2.1.3 | L2 | Business-logic limits documented per user and globally. | Met | `docs/design/2026-10-11-scholarsync-design.md` uploads per hour (§7, line 678), support messages per day (line 548), import rows and size (line 459). |
| V2.2.1 | L1 | Validate input against allowlists, patterns and ranges. | Met | Django forms with `ChoiceField`s and bounds; upload intents type-checked and allowlisted (`apps/files/views.py:49`, `apps/files/services.py:75`). |
| V2.2.2 | L1 | Validation is enforced server-side, not only in the client. | Met | All checks live in forms and services (`apps/files/services.py:75`); `apps/files/tests/test_views.py::test_intent_wrong_field_types`. |
| V2.2.3 | L2 | Combinations of related data items are checked against rules. | Met | Cross-field `clean()` methods, e.g. report period order (`apps/reports/forms.py:59`) and bulk action with ids (`apps/money/forms.py:72`). |
| V2.3.1 | L1 | Business flows run in the expected step order without skipping. | Met | Status changes go through `assert_transition` (`apps/core/transitions.py:20`); `apps/core/tests/test_transitions.py::test_disallowed_transition_raises_with_labels`. |
| V2.3.2 | L2 | Business-logic limits are implemented as documented. | Met | Upload starts per hour (`apps/files/services.py:93`), support messages per day (`apps/workspace/support.py:25`), import rows (`apps/awards/tabular.py:21`); `apps/workspace/tests/test_support.py::test_sixth_message_in_24_hours_is_refused_and_keeps_the_text`. |
| V2.3.3 | L2 | Business operations are transactional: all succeed or roll back. | Met | Services are `@transaction.atomic` (`apps/files/services.py:250`, `apps/accounts/services.py:260`). |
| V2.3.4 | L2 | Locking prevents double-booking limited resources. | Met | Row locks on payouts and budgets (`apps/money/services.py:269`, `apps/money/services.py:531`); term changes take an advisory lock (`apps/programs/services.py:119`). |
| V2.4.1 | L2 | Anti-automation limits excessive calls to functions. | Met | allauth rate limits on login, signup, reset and reauthentication (database cache, `config/settings.py:287`); upload starts per hour (`apps/files/services.py:98`); support messages per day (`apps/workspace/support.py:52`). |

## V3 Web Frontend Security

14 Met, 2 Not applicable, 3 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V3.2.1 | L1 | Prevent responses rendering in the wrong context (APIs, uploads). | Met | Uploads are served only from the storage origin as attachments with the sniffed type (`apps/files/services.py:304`); JSON endpoints answer `application/json` with `nosniff` (`config/settings.py:416`). |
| V3.2.2 | L1 | Show text with safe functions such as textContent. | Met | `frontend/src/toast.ts:72` and `frontend/src/upload.ts:175` use `textContent`; no `innerHTML` in `frontend/src/`. |
| V3.3.1 | L1 | Cookies are Secure and use the __Host- or __Secure- prefix. | Met | Secure everywhere in production; `__Host-sessionid`, `__Host-csrftoken` and `__Host-theme` (the light/dark choice: HttpOnly, SameSite=Lax, one year) (`config/settings.py`, `tests/test_asvs_gaps.py::test_production_cookies_use_the_host_prefix`); flash messages live in the session, so no other cookie is set. |
| V3.3.2 | L2 | Each cookie's SameSite value fits its purpose. | Met | `SESSION_COOKIE_SAMESITE = "Lax"` (`config/settings.py:422`); the CSRF and messages cookies keep Django's `Lax` default. |
| V3.3.3 | L2 | Cookies use the __Host- prefix unless shared with other hosts. | Met | `__Host-` prefix in production (`tests/test_asvs_gaps.py::test_production_cookies_use_the_host_prefix`). |
| V3.3.4 | L2 | Cookies not meant for scripts are HttpOnly; session token only in cookie. | Met | Session and CSRF cookies are HttpOnly (`config/settings.py`, `tests/test_asvs_gaps.py::test_csrf_cookie_is_httponly`); htmx takes the token from `hx-headers`. |
| V3.4.1 | L1 | HSTS on all responses, at least one year, including subdomains. | Met | `config/settings.py:411`; `apps/core/tests/test_security_headers.py::test_tests_run_with_production_security_settings`. |
| V3.4.2 | L1 | CORS Access-Control-Allow-Origin is fixed or allowlisted. | Met | The app sends no CORS headers (no CORS middleware in `config/settings.py:170`); the bucket's CORS names the site origin (`docs/HOSTING.md:125`). |
| V3.4.3 | L2 | A Content-Security-Policy restricts scripts, objects and base URI. | Met | `config/settings.py:458`; `apps/core/tests/test_security_headers.py::test_csp_enforced_by_default`. |
| V3.4.4 | L2 | Every response carries X-Content-Type-Options: nosniff. | Met | `config/settings.py:416`; `apps/core/tests/test_security_headers.py::test_security_headers_on_404`. |
| V3.4.5 | L2 | A Referrer-Policy stops leaking sensitive data to third parties. | Met | `same-origin` (`config/settings.py:418`); `apps/core/tests/test_security_headers.py::test_security_headers_on_success`. |
| V3.4.6 | L2 | CSP frame-ancestors forbids embedding by default. | Met | `frame-ancestors 'none'` (`config/settings.py:465`) plus `X-Frame-Options: DENY` (`config/settings.py:419`). |
| V3.5.1 | L1 | Cross-origin requests to sensitive functions are rejected (CSRF tokens). | Met | `CsrfViewMiddleware` (`config/settings.py:178`), with no `csrf_exempt` in `apps/` or `config/` (allauth's unused `google_login_by_token` exempts itself and is removed by the V10.5.1 fix); `apps/core/tests/test_base_template.py::test_body_sends_the_csrf_token_with_htmx_requests`. |
| V3.5.2 | L1 | If relying on CORS preflight, no request can bypass it. | Not applicable | The app relies on CSRF tokens, not on CORS preflight. |
| V3.5.3 | L1 | Sensitive functions use POST/PUT/PATCH/DELETE, not GET. | Met | Logout is POST only (`config/settings.py:313`; `apps/accounts/tests/test_login.py::test_logout_needs_post`); upload endpoints are `require_POST` (`apps/files/views.py:69`). Opening a notification marks it read on GET, which is low-risk. |
| V3.5.4 | L2 | Separate applications live on separate hostnames. | Met | User files come from the storage origin, never the app origin (`apps/files/views.py:131`); the design kit is refused in production (`config/settings.py:129`). |
| V3.5.5 | L2 | postMessage handlers check origin and message syntax. | Not applicable | No `postMessage` use in `frontend/src/`. |
| V3.7.1 | L2 | Only supported, secure client-side technologies are used. | Met | htmx 2 and strict TypeScript (`frontend/package.json:28`); no plugins (`object-src 'none'`, `config/settings.py:468`). |
| V3.7.2 | L2 | Automatic redirects to other hosts only to allowlisted destinations. | Met | Notification links checked with `url_has_allowed_host_and_scheme` (`apps/workspace/notification_views.py:109`); allauth validates `next`; downloads redirect only to the configured storage. |

## V4 API and Web Service

3 Met, 6 Not applicable, 1 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V4.1.1 | L1 | Content-Type matches the body and includes a charset. | Met | Text answers carry `text/plain; charset=utf-8` (`apps/files/views.py`, `tests/test_asvs_gaps.py::test_download_503_has_a_charset`); pages and JSON use Django's charset. |
| V4.1.2 | L2 | Only user-facing endpoints redirect HTTP to HTTPS. | Met | Every endpoint is browser-facing (the JSON upload endpoints are called by the page's own script under HSTS); `SECURE_SSL_REDIRECT` (`config/settings.py:410`). |
| V4.1.3 | L2 | Intermediary-set headers cannot be overridden by the end user. | Met | Client IP from `X-Forwarded-For` with a trusted proxy count (`config/settings.py:334`, `compose.production.yaml:31`); `docs/HOSTING.md:185` tells the proxy to append or overwrite. |
| V4.2.1 | L2 | All components agree on HTTP message boundaries (no smuggling). | Met | gunicorn 26.2.0 (`uv.lock`, `Dockerfile:47`) refuses ambiguous `Content-Length`/`Transfer-Encoding`; the TLS proxy is the operator's. |
| V4.3.1 | L2 | Limit GraphQL query depth or cost. | Not applicable | No GraphQL. |
| V4.3.2 | L2 | Disable GraphQL introspection in production. | Not applicable | No GraphQL. |
| V4.4.1 | L1 | WebSockets use WSS. | Not applicable | No WebSockets. |
| V4.4.2 | L2 | Check Origin during the WebSocket handshake. | Not applicable | No WebSockets. |
| V4.4.3 | L2 | Dedicated WebSocket tokens follow session rules. | Not applicable | No WebSockets. |
| V4.4.4 | L2 | WebSocket tokens come from the authenticated HTTPS session. | Not applicable | No WebSockets. |

## V5 File Handling

6 Met, 0 Not applicable, 3 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V5.1.1 | L2 | Documentation defines file types, extensions and sizes, including unpacked size. | Met | Spec §7 lists each purpose's types and sizes, and the XLSX entry and unpacked-size caps. |
| V5.2.1 | L1 | Accept only file sizes the app can process without DoS. | Met | Per-purpose limits (`apps/files/policy.py:55`) and a presigned PUT that signs the length (`apps/files/storage.py:103`); `apps/files/tests/test_storage.py::test_presigned_put_signs_type_and_length`. |
| V5.2.2 | L1 | Check the file extension and that contents match the type. | Met | A 4 KB `filetype` sniff must equal the declared type (`apps/files/services.py:171`) and downloads take the sniffed type's extension (`apps/files/names.py:29`); `apps/files/tests/test_services.py::test_confirm_rejects_fake_pdf`. |
| V5.2.3 | L2 | Check archives' uncompressed size and file count before unpacking. | Met | `apps/awards/tabular.py` refuses more than 100 archive entries or 10 MB unpacked before reading (`tests/test_asvs_gaps.py::test_xlsx_with_too_many_entries_is_refused`). |
| V5.3.1 | L1 | Uploaded files in public folders are never executed server-side. | Met | Files go straight to a private bucket and never through Django (`apps/files/services.py:136`); nothing is written to the app's disk. |
| V5.3.2 | L1 | File paths use internal data, never user-supplied names. | Met | Object keys are `pending/<uuid>` and `files/<purpose>/<uuid>` (`apps/files/models.py:8`, `apps/files/models.py:68`). |
| V5.4.1 | L2 | Ignore user filenames and set a Content-Disposition filename on download. | Met | Names cleaned (`apps/files/names.py:14`) and sent as an attachment (`apps/files/services.py:307`). |
| V5.4.2 | L2 | Served file names are encoded or sanitised (RFC 6266). | Met | `apps/files/names.py:37`; `apps/files/tests/test_names.py::test_content_disposition_has_ascii_fallback_and_utf8`. |
| V5.4.3 | L2 | Scan untrusted files with an antivirus before serving them. | Met | Optional, the operator's choice: with `CLAMAV_HOST` set, confirm streams each file to clamd (`apps/files/scanning.py:39`, `apps/files/services.py:152`) and rejects a hit; clamd down fails closed (503, file stays pending). `apps/files/tests/test_scanning.py::test_infected_file_is_rejected_with_malware_reason`, `apps/files/tests/test_scanning.py::test_clamd_down_answers_503_and_leaves_pending`; `docs/HOSTING.md` shows the `clamav/clamav` service. |

## V6 Authentication

18 Met, 11 Not applicable, 6 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V6.1.1 | L1 | Docs define rate limiting and anti-automation against credential attacks. | Met | `docs/security/controls.md` (Authentication and rate limits): every limit, the 5-minute per-account lockout and the proxy count. |
| V6.1.2 | L2 | A list of context-specific words banned from passwords is documented. | Met | `docs/security/controls.md` lists the site words; `apps/accounts/validators.py`. |
| V6.1.3 | L2 | All authentication pathways and their strengths are documented. | Met | `docs/design/2026-10-11-scholarsync-design.md` §10 (line 836): password, Google (students only), reset and reauthentication (by password, authenticator code or a code emailed to a verified address, rev 39); claim links in §4.3; staff set-password links in §9. |
| V6.2.1 | L1 | Passwords are at least 8 characters (15 recommended). | Met | Minimum 10 (`config/settings.py:365`). |
| V6.2.2 | L1 | Users can change their password. | Met | allauth's password change view (`config/urls.py:53`); `apps/accounts/tests/test_login.py::test_password_reset_and_change_are_audited`. |
| V6.2.3 | L1 | Password change requires the current and new password. | Met | allauth `ChangePasswordForm.oldpassword`, checked with `check_password` (allauth 65.20.1, `uv.lock`). |
| V6.2.4 | L1 | New passwords are checked against at least the top 3000 passwords. | Met | `CommonPasswordValidator` (20,000 common passwords, `config/settings.py:367`). |
| V6.2.5 | L1 | Passwords of any composition are allowed; no character-class rules. | Met | No composition rules: `NumericPasswordValidator` is gone; length, similarity, common-password and site-word checks remain (`config/settings.py:367`). `config/tests/test_settings.py::test_numeric_validator_removed`. |
| V6.2.6 | L1 | Password fields use type=password. | Met | allauth `PasswordField` renders `PasswordInput` (allauth pinned at `pyproject.toml:20`); `apps/accounts/tests/test_pages.py::test_every_input_has_a_label` renders the login, signup and reset forms. |
| V6.2.7 | L1 | Paste, browser helpers and password managers are permitted. | Met | No script touches password inputs: `frontend/src/` has no paste or key handlers, and `tests/test_rendered_pages.py::test_every_get_page_is_csp_clean` rejects inline `on*` handlers; allauth sets `autocomplete` on password fields. |
| V6.2.8 | L1 | The password is verified exactly as received, without changes. | Met | allauth `PasswordField` sets `strip=False` (allauth pinned at `pyproject.toml:20`); Django hashes the raw value. |
| V6.2.9 | L2 | Passwords of at least 64 characters are permitted. | Met | No maximum length in `AUTH_PASSWORD_VALIDATORS` (`config/settings.py:361`) or on allauth's `PasswordField`. |
| V6.2.10 | L2 | No periodic password rotation is required. | Met | No password-age setting or expiry code exists; validators are length and content only (`config/settings.py:361`). |
| V6.2.11 | L2 | The context-specific word list is used to block easy passwords. | Met | `apps/accounts/validators.py` (`SiteWordsValidator`, in `AUTH_PASSWORD_VALIDATORS`); `tests/test_asvs_gaps.py::test_password_with_a_site_word_is_refused`. |
| V6.2.12 | L2 | New passwords are checked against breached-password sets. | Met | New passwords are checked against Have I Been Pwned's k-anonymity range API in production (`apps/accounts/breach.py:39`, `config/settings.py:372`); only five hex characters of the SHA-1 leave the server; fails open with a log line. `apps/accounts/tests/test_breach.py::test_breached_password_refused`, `apps/accounts/tests/test_breach.py::test_only_five_hex_characters_are_sent`. |
| V6.3.1 | L1 | Credential-stuffing and brute-force controls are implemented. | Met | allauth `login_failed` limit (5 per 5 minutes per account, 10 per minute per IP); `apps/accounts/tests/test_login.py::test_repeated_failed_logins_are_rate_limited`. |
| V6.3.2 | L1 | No default accounts such as root or admin exist. | Met | Production never installs the demo accounts (`config/settings.py:166`); the first office account is created with its own password (`docs/HOSTING.md:249`). |
| V6.3.3 | L2 | Multi-factor authentication (or combined factors) is required. | Met | `allauth.mfa` (TOTP and recovery codes); staff and office accounts must set it up before any other page in production (`apps/accounts/mfa_policy.py:25`, `config/settings.py:323`). Students are not required (risk-based: own data only). `apps/accounts/tests/test_mfa.py::test_staff_without_authenticator_is_sent_to_activation`, `apps/accounts/tests/test_mfa.py::test_totp_sign_in_round_trip`. |
| V6.3.4 | L2 | No undocumented pathways; strength enforced consistently. | Met | Google sign-in can never reach staff or office accounts (`apps/accounts/adapters.py:99`; `apps/accounts/tests/test_google.py::test_a_google_email_match_never_signs_in_a_privileged_account`); every URL is in `tests/test_permission_matrix.py::test_every_url_is_in_the_matrix`. |
| V6.4.1 | L1 | Initial passwords and activation codes are random, short-lived or single-use. | Met | Claim tokens are `secrets.token_urlsafe(32)`, stored hashed, single-use (`apps/students/services.py:296`); staff set-password links are Django reset tokens (`apps/accounts/services.py:147`) that die once a password is set. |
| V6.4.2 | L1 | No password hints or secret questions. | Met | Signup asks only email and password (`config/settings.py:304`). |
| V6.4.3 | L2 | Password reset is secure and does not bypass MFA. | Met | allauth emailed reset key (through the outbox); `apps/accounts/tests/test_login.py::test_password_reset_sends_the_key_through_the_outbox`. A reset never signs anyone in (`ACCOUNT_LOGIN_ON_PASSWORD_RESET` unset, allauth's default off), so the next sign-in still asks for the authenticator code. |
| V6.4.4 | L2 | A lost MFA factor needs identity proofing like enrolment. | Met | A lost factor is an office action, behind the office's own password, audited and ending the account's sessions (`apps/accounts/services.py`, `remove_mfa`; `apps/accounts/tests/test_mfa.py::test_office_removes_a_staff_authenticator_after_password`); staff can't remove their own while 2FA is required (`apps/accounts/tests/test_mfa.py::test_staff_cannot_switch_off_their_own_authenticator`). The new factor is enrolled the way the first was: signed in with the password. The office should confirm who is asking before removing it (`docs/HOSTING.md`, the `MFA_REQUIRED_FOR_STAFF` row). |
| V6.5.1 | L2 | Lookup secrets, OOB codes and TOTPs are single-use. | Met | TOTP codes are refused a second time within their period (allauth marks each used code in the shared database cache); recovery codes are single-use (allauth's `used_mask`). |
| V6.5.2 | L2 | Low-entropy lookup secrets are stored hashed. | Met | Recovery codes are 8 digits derived by HMAC from a per-account seed, so the seed must stay recoverable and can't be hashed; it is encrypted at rest instead, like the TOTP secret (Fernet, keys derived with HKDF from `DJANGO_SECRET_KEY` and its fallbacks; `apps/accounts/mfa_secrets.py`, `apps/accounts/adapters.py`). Existing rows are encrypted by migration `accounts.0003`. `apps/accounts/tests/test_mfa_secrets.py`. The maintainer's decision, 2026-11-19 (spec revision 24). |
| V6.5.3 | L2 | Lookup secrets, OOB codes and TOTP seeds come from a CSPRNG. | Met | TOTP secrets come from `secrets.token_bytes(20)` and recovery-code seeds from `secrets.token_hex(40)` (allauth). |
| V6.5.4 | L2 | Lookup secrets and OOB codes have at least 20 bits of entropy. | Met | Recovery codes are 8 digits (about 26.6 bits each); no out-of-band codes. |
| V6.5.5 | L2 | OOB requests and TOTPs have short defined lifetimes. | Met | TOTP codes last one 30-second period with no tolerance window (allauth defaults `MFA_TOTP_PERIOD`, `MFA_TOTP_TOLERANCE`); no out-of-band authentication. |
| V6.6.1 | L2 | PSTN/SMS OTPs only to validated numbers, with stronger alternatives. | Not applicable | No phone or SMS authentication. |
| V6.6.2 | L2 | OOB codes are bound to their original authentication request. | Not applicable | No out-of-band authentication. |
| V6.6.3 | L2 | Code-based OOB authentication is rate limited. | Not applicable | No out-of-band authentication. |
| V6.8.1 | L2 | Identities from multiple IdPs cannot be spoofed across providers. | Met | Only Google besides passwords; Google links by verified email only to student accounts (`config/settings.py:328`, `apps/accounts/adapters.py:114`); `apps/accounts/tests/test_google.py::test_a_google_email_match_never_signs_in_a_privileged_account`. |
| V6.8.2 | L2 | Signatures on authentication assertions (JWT, SAML) are always validated. | Met | Google provider (`config/settings.py:344`): allauth checks the ID token's signature on the token-login route and, in the code flow, takes it straight from Google's token endpoint over verified TLS (OIDC Core 3.1.3.7). |
| V6.8.3 | L2 | SAML assertions are used only once. | Not applicable | No SAML. |
| V6.8.4 | L2 | Required IdP authentication strength or recency is verified. | Not applicable | The app requires no particular strength or recency from Google; reauthentication is local. |

## V7 Session Management

8 Met, 0 Not applicable, 10 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V7.1.1 | L2 | Inactivity and absolute session lifetimes are documented and justified. | Met | `docs/security/controls.md` (Sessions) documents the 12-hour lifetime and why; an idle timeout and hard cap are open (V7.3.1, V7.3.2). |
| V7.1.2 | L2 | Docs define allowed concurrent sessions and behaviour at the limit. | Met | `docs/security/controls.md` (Sessions): concurrent sessions are unlimited, with the reason. |
| V7.1.3 | L2 | Federated (SSO) session lifetimes and termination are documented. | Met | `docs/security/controls.md` (Sessions): Google only proves the email; the local session follows the local rules. |
| V7.2.1 | L1 | Session tokens are verified by a trusted backend. | Met | Database-backed Django sessions (`config/settings.py:176`). |
| V7.2.2 | L1 | Session tokens are dynamic, not static API secrets. | Met | Django session keys are generated per sign-in (`config/settings.py:176`). |
| V7.2.3 | L1 | Reference tokens are unique, CSPRNG-made, with 128+ bits of entropy. | Met | Django database sessions (`config/settings.py:176`): keys are 32 characters from `get_random_string` (`secrets`), about 165 bits. |
| V7.2.4 | L1 | A new session token is issued on authentication and re-authentication. | Met | Sign-in rotates the key (Django `login()`); all three reauthentication confirmations do too, by password, by authenticator code or by emailed code (`apps/accounts/reauth.py:19`, mounted at allauth's paths in `config/urls.py`). `apps/accounts/tests/test_sessions.py::test_reauthentication_cycles_the_session_key`, `apps/accounts/tests/test_sessions.py::test_authenticator_reauthentication_cycles_the_session_key`, `apps/accounts/tests/test_sessions.py::test_code_reauthentication_cycles_the_session_key`. |
| V7.3.1 | L2 | An inactivity timeout forces re-authentication per risk analysis. | Met | Idle limits: 30 minutes for staff and the office, 60 for students (`config/settings.py:425`), enforced per request (`apps/accounts/session_policy.py:52`), with a warning dialog first. `apps/accounts/tests/test_session_policy.py::test_staff_idle_31_minutes_is_signed_out_with_message`, `apps/accounts/tests/test_session_policy.py::test_student_idle_59_minutes_is_still_signed_in`. |
| V7.3.2 | L2 | An absolute maximum session lifetime forces re-authentication. | Met | Every session ends 12 hours after sign-in whatever the activity (`signed_in_at`, `apps/accounts/session_policy.py:52`, `config/settings.py:423`). `apps/accounts/tests/test_session_policy.py::test_absolute_12_hours_ends_session_even_when_active`. |
| V7.4.1 | L1 | Logout or expiry stops any further use of the session. | Met | Django `logout()` flushes the database session; `cleanup` runs `clearsessions` (`apps/core/tests/test_commands.py::test_cleanup_clears_expired_sessions`). |
| V7.4.2 | L1 | Disabling or deleting an account ends all its sessions. | Met | `apps/accounts/services.py:289`; `apps/office/tests/test_staff.py::test_deactivate_ends_sessions_and_blocks_sign_in`. |
| V7.4.3 | L2 | Offer to end other sessions after an authentication factor changes. | Met | `AuthenticationMiddleware` (`config/settings.py:179`) checks the session auth hash, which ends every other session on a password change or reset; allauth keeps only the current one (`LOGOUT_ON_PASSWORD_CHANGE` default `False`). |
| V7.4.4 | L2 | Every authenticated page has visible logout. | Met | App layouts (`templates/layouts/app.html`) and signed-in account pages (`templates/layouts/auth.html`) offer Sign out (`tests/test_asvs_gaps.py::test_signed_in_account_pages_offer_sign_out`). |
| V7.4.5 | L2 | Administrators can end sessions for one user or all users. | Met | The office signs a staff or office account out everywhere, behind the password (`apps/office/staff_views.py:123`, `apps/accounts/services.py:216`); the operator ends any account's sessions with `manage.py end_sessions --email` (`apps/accounts/management/commands/end_sessions.py`); both audited by id. `apps/accounts/tests/test_sessions.py::test_office_signs_staff_out_everywhere_after_password`, `apps/accounts/tests/test_sessions.py::test_end_sessions_command_by_email_audited`. |
| V7.5.1 | L2 | Full re-authentication before changing email or other auth attributes. | Met | `ACCOUNT_REAUTHENTICATION_REQUIRED` (`config/settings.py:311`); `apps/accounts/tests/test_login.py::test_email_change_asks_to_reauthenticate_after_five_minutes`. |
| V7.5.2 | L2 | Users can view and terminate their active sessions. | Met | `allauth.usersessions` lists the account's sessions at `/accounts/sessions/` (account menu); signing the others out asks for the password again (`apps/accounts/reauth.py:48`). `apps/accounts/tests/test_sessions.py::test_user_lists_and_ends_other_sessions`. |
| V7.6.1 | L2 | RP/IdP session lifetimes and termination behave as documented. | Met | Behaviour as documented in `docs/security/controls.md` (Sessions): signing out here or at Google affects only that side. |
| V7.6.2 | L2 | Creating a session needs user consent or explicit action. | Met | Google sign-in starts only from a POST on allauth's confirm page; `tests/test_permission_matrix.py::test_google_with_keys_shows_confirm_page_and_rejects_a_bare_callback`. |

## V8 Authorization

6 Met, 0 Not applicable, 1 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V8.1.1 | L1 | Docs define function-level and data-specific access rules. | Met | `docs/design/2026-10-11-scholarsync-design.md` §6 (line 602) with the capability table. |
| V8.1.2 | L2 | Docs define field-level read and write access rules. | Met | `docs/security/controls.md` (Who reads and writes what). |
| V8.2.1 | L1 | Function-level access requires explicit permission. | Met | Role and program mixins (`apps/core/permissions.py:57`, `apps/core/permissions.py:78`); `tests/test_permission_matrix.py::test_access`. |
| V8.2.2 | L1 | Data access is restricted per item (IDOR/BOLA). | Met | Scoped selectors answer 404 (`apps/files/views.py:124`); `apps/files/tests/test_selectors.py::test_student_cannot_download_another_students_document`, `apps/files/tests/test_views.py::test_other_student_gets_404`. |
| V8.2.3 | L2 | Field-level access is restricted (BOPLA). | Met | Forms list their fields explicitly (no `fields = "__all__"`); `apps/accounts/tests/test_signup.py::test_signup_ignores_role_and_staff_fields`. |
| V8.3.1 | L1 | Authorisation is enforced server-side, not in client code. | Met | Checks in view mixins and services (`apps/core/permissions.py:13`, `apps/files/services.py:79`). |
| V8.4.1 | L2 | Cross-tenant controls stop actions on other tenants. | Met | Programs are the tenants: staff URLs are scoped to the program in the URL (`apps/core/permissions.py:97`); the matrix tests other-program staff (`tests/test_permission_matrix.py::test_access`). |

## V9 Self-contained Tokens

5 Met, 1 Not applicable, 1 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V9.1.1 | L1 | Self-contained tokens are validated by signature or MAC first. | Met | Google ID tokens (`config/settings.py:344`): signature checked against Google's keys on the token-login route; code-flow tokens come straight from Google over verified TLS (OIDC Core 3.1.3.7). The app issues no tokens. |
| V9.1.2 | L1 | Only allowlisted algorithms create or verify tokens. | Met | allauth's One Tap token route, the only place a token's `alg` was read, answers 404 (`config/urls.py`, `tests/test_asvs_gaps.py::test_google_login_by_token_is_404_even_with_keys`); the code flow gets the ID token from Google over TLS. |
| V9.1.3 | L1 | Token verification keys come from trusted, pre-configured sources. | Met | allauth (`pyproject.toml:20`) fetches keys only from Google's fixed certificate URL and checks the fixed issuer. |
| V9.2.1 | L1 | Tokens are accepted only within their validity window. | Met | allauth `jwtkit.verify_and_decode` sets `verify_exp` (allauth pinned at `pyproject.toml:20`). |
| V9.2.2 | L2 | Tokens are checked for the correct type and purpose. | Met | Only Google ID tokens are accepted (`config/settings.py:344`), with issuer and audience checked; access tokens are never used for authorisation. |
| V9.2.3 | L2 | Tokens are accepted only for the intended audience. | Met | allauth checks `aud` against the configured client ID (`config/settings.py:347`, `verify_aud`). |
| V9.2.4 | L2 | Issuers sharing a key across audiences add audience restrictions. | Not applicable | The app issues no tokens. |

## V10 OAuth and OIDC

6 Met, 22 Not applicable, 1 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V10.1.1 | L2 | Tokens are sent only to components that need them. | Met | Google tokens stay server-side and are not stored: `SOCIALACCOUNT_STORE_TOKENS` is left at `False` (`config/settings.py:344` sets no override). |
| V10.1.2 | L2 | The client accepts codes or ID tokens only from flows it started. | Met | allauth binds the callback to a session-stored `state` (10-minute TTL); `tests/test_permission_matrix.py::test_google_with_keys_shows_confirm_page_and_rejects_a_bare_callback`. |
| V10.2.1 | L2 | The code flow is protected against CSRF (PKCE or state). | Met | allauth's `state` parameter, checked against the session on the callback (PKCE is off for Google); `tests/test_permission_matrix.py::test_google_with_keys_shows_confirm_page_and_rejects_a_bare_callback`. |
| V10.2.2 | L2 | Defend against mix-up attacks with several authorization servers. | Not applicable | Only one authorization server (Google). |
| V10.3.1 | L2 | Resource server checks the access token audience. | Not applicable | No resource server; the app accepts no access tokens. |
| V10.3.2 | L2 | Resource server enforces delegated authorisation claims. | Not applicable | No resource server. |
| V10.3.3 | L2 | Resource server identifies users by non-reassignable claims. | Not applicable | No resource server. |
| V10.3.4 | L2 | Resource server checks authentication strength or recency claims. | Not applicable | No resource server. |
| V10.4.1 | L1 | Authorization server validates redirect URIs exactly. | Not applicable | No OAuth authorization server; Google sign-in is an OIDC client via allauth. |
| V10.4.2 | L1 | Authorization codes are single-use. | Not applicable | No OAuth authorization server. |
| V10.4.3 | L1 | Authorization codes are short-lived. | Not applicable | No OAuth authorization server. |
| V10.4.4 | L1 | Clients get only the grants they need; no implicit or password grants. | Not applicable | No OAuth authorization server. |
| V10.4.5 | L1 | Refresh-token replay is mitigated for public clients. | Not applicable | No OAuth authorization server. |
| V10.4.6 | L2 | Authorization server requires PKCE for the code grant. | Not applicable | No OAuth authorization server. |
| V10.4.7 | L2 | Dynamic client registration is safe. | Not applicable | No OAuth authorization server. |
| V10.4.8 | L2 | Refresh tokens have an absolute expiry. | Not applicable | No OAuth authorization server. |
| V10.4.9 | L2 | Users can revoke refresh and reference access tokens. | Not applicable | No OAuth authorization server. |
| V10.4.10 | L2 | Confidential clients authenticate on back-channel requests. | Not applicable | No OAuth authorization server. |
| V10.4.11 | L2 | Clients get only the scopes they need. | Not applicable | No OAuth authorization server. |
| V10.5.1 | L2 | The OIDC client prevents ID-token replay (nonce). | Met | The token route without a nonce check answers 404 (`tests/test_asvs_gaps.py::test_google_login_by_token_is_404_even_with_keys`); the code flow uses state and PKCE through allauth. |
| V10.5.2 | L2 | Users are identified by the non-reassignable `sub` claim. | Met | allauth's Google provider (`config/settings.py:344`) takes `sub` as the account UID (`extract_uid`). |
| V10.5.3 | L2 | Reject authorization-server metadata with a mismatched issuer. | Met | No metadata discovery: allauth uses Google's fixed endpoints and issuer (`config/settings.py:344` sets only keys and scopes). |
| V10.5.4 | L2 | ID token `aud` must equal the client ID. | Met | allauth passes `audience=app.client_id` with `verify_aud` (client ID from `config/settings.py:347`). |
| V10.5.5 | L2 | Back-channel logout tokens are validated. | Not applicable | No OIDC back-channel logout. |
| V10.6.1 | L2 | OpenID Provider allows only safe response modes. | Not applicable | Not an OpenID Provider. |
| V10.6.2 | L2 | OpenID Provider resists forced-logout DoS. | Not applicable | Not an OpenID Provider. |
| V10.7.1 | L2 | Authorization server gets user consent for each request. | Not applicable | No OAuth authorization server. |
| V10.7.2 | L2 | Consent prompts explain clearly what is granted. | Not applicable | No OAuth authorization server. |
| V10.7.3 | L2 | Users can review, change and revoke consents. | Not applicable | No OAuth authorization server. |

## V11 Cryptography

7 Met, 5 Not applicable, 2 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V11.1.1 | L2 | A key-management policy and key lifecycle are documented. | Met | `docs/HOSTING.md` (step 2 and §10 Runbook, Rotate a secret) and `docs/security/controls.md` (Keys and cryptography). |
| V11.1.2 | L2 | A cryptographic inventory of keys, algorithms and certificates is kept. | Met | `docs/security/controls.md` (Keys and cryptography): the algorithm table. |
| V11.2.1 | L2 | Cryptography uses industry-validated implementations. | Met | argon2-cffi (`pyproject.toml:21`), Python `hashlib`/`hmac`/`secrets` (`apps/core/audit.py:19`), Django signing. |
| V11.2.2 | L2 | Crypto is agile: algorithms and parameters can be swapped. | Met | `PASSWORD_HASHERS` upgrades hashes on sign-in (`config/settings.py:355`); Django signing reads the algorithm from settings. |
| V11.2.3 | L2 | All primitives give at least 128 bits of security. | Met | HMAC-SHA256 and SHA-256 (`apps/core/audit.py:24`); Argon2; `check --deploy` in CI enforces a long `SECRET_KEY` (`.github/workflows/ci.yml:106`). |
| V11.3.1 | L1 | No insecure block modes (ECB) or weak padding. | Not applicable | The app encrypts nothing itself; TLS and at-rest encryption are the providers'. |
| V11.3.2 | L1 | Only approved ciphers and modes such as AES-GCM. | Not applicable | The app encrypts nothing itself. |
| V11.3.3 | L2 | Encrypted data is protected with authenticated encryption. | Not applicable | The app encrypts nothing itself. |
| V11.4.1 | L1 | Only approved hash functions; no MD5 for crypto. | Met | SHA-256 everywhere (`apps/core/audit.py:24`, `apps/files/services.py:174`, `apps/students/selectors.py:91`). `PBKDF2SHA1PasswordHasher` (`config/settings.py:358`) can only verify old hashes, and there are none. |
| V11.4.2 | L2 | Passwords are stored with an approved, tuned password hash. | Met | Argon2 first (`config/settings.py:356`), so every new or changed password is Argon2id. |
| V11.4.3 | L2 | Integrity hashes are collision-resistant, at least 256 bits. | Met | SHA-256 file digests (`apps/files/services.py:174`). |
| V11.4.4 | L2 | Keys derived from passwords use a stretching KDF. | Not applicable | No keys are derived from passwords. |
| V11.5.1 | L2 | Non-guessable values come from a CSPRNG with 128+ bits. | Met | `secrets.token_urlsafe(32)` claim tokens (`apps/students/services.py:296`); Django session keys and allauth keys use `secrets`. |
| V11.6.1 | L2 | Only approved algorithms for key generation and signatures. | Not applicable | The app generates no keys and makes no digital signatures. |

## V12 Secure Communication

2 Met, 4 Not applicable, 3 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V12.1.1 | L1 | Only TLS 1.2 and 1.3 are enabled, 1.3 preferred. | Not applicable | TLS terminates at the operator's proxy (`docs/HOSTING.md:185`). |
| V12.1.2 | L2 | Only recommended cipher suites, strongest preferred. | Not applicable | TLS terminates at the operator's proxy (`docs/HOSTING.md:185`). |
| V12.1.3 | L2 | mTLS client certificates are validated before use. | Not applicable | No mTLS. |
| V12.2.1 | L1 | TLS for all client connections, with no plaintext fallback. | Met | `SECURE_SSL_REDIRECT` and HSTS in production (`config/settings.py:410`); `apps/core/tests/test_security_headers.py::test_plain_http_redirects_to_https`. |
| V12.2.2 | L1 | External services use publicly trusted certificates. | Not applicable | The certificate belongs to the operator's proxy. |
| V12.3.1 | L2 | All inbound and outbound connections (database, mail, storage) use TLS. | Met | Production refuses to start with a plaintext database (no `sslmode`), `smtp://`, an `http://` storage endpoint or a clamd on another machine, unless `ALLOW_PLAINTEXT_SERVICES=true` (`config/plaintext.py`, `config/settings.py:275`); loopback and Docker service names are exempt. `config/tests/test_settings.py::test_production_refuses_plaintext_smtp_to_another_host`, `config/tests/test_settings.py::test_production_refuses_database_without_tls_to_another_host`, `config/tests/test_settings.py::test_production_refuses_clamd_on_another_host`. |
| V12.3.2 | L2 | TLS clients validate server certificates. | Met | `docs/HOSTING.md` step 4 recommends `sslmode=verify-full` with the provider's CA; SMTP and S3 clients verify certificates by default. |
| V12.3.3 | L2 | Internal HTTP services use TLS with no fallback. | Met | The same guard refuses an `http://` `S3_ENDPOINT_URL` or `S3_PUBLIC_ENDPOINT_URL` on another host (`config/plaintext.py`). `config/tests/test_settings.py::test_production_refuses_http_storage_to_another_host`. |
| V12.3.4 | L2 | Internal TLS uses trusted certificates or pinned internal CAs. | Met | boto3 verifies certificates by default and `apps/files/storage.py:43` never sets `verify=False`; Django's SMTP backend uses `ssl.create_default_context()`. |

## V13 Configuration

10 Met, 2 Not applicable, 1 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V13.1.1 | L2 | All communication needs and external services are documented. | Met | `docs/design/2026-10-11-scholarsync-design.md` §11 Providers (line 921) and `docs/HOSTING.md:89`. |
| V13.2.1 | L2 | Backend component communications are authenticated. | Met | Database, storage and SMTP credentials in `DATABASE_URL`, `S3_*` and `EMAIL_URL` (`config/settings.py:211`, `config/settings.py:249`, `config/settings.py:223`). |
| V13.2.2 | L2 | Backend communications use least-privilege accounts. | Met | Migrations run as the owner through `DATABASE_URL_MIGRATIONS` (`docker/entrypoint.sh:12`), which is unset before the app starts; `docs/HOSTING.md` gives the row-only runtime role, with `UPDATE`, `DELETE` and `TRUNCATE` revoked on `core_auditevent`; the image's code is root-owned (`Dockerfile:27`). `tests/test_docker_files.py::test_entrypoint_prefers_the_migrations_url`, `tests/test_docker_files.py::test_app_code_is_not_owned_by_the_runtime_user`. |
| V13.2.3 | L2 | Service credentials are never defaults. | Met | Production refuses the public explore storage key and placeholder secret keys (`config/settings.py:259`, `config/settings.py:62`, `config/settings.py:68`). |
| V13.2.4 | L2 | An allowlist defines external resources the app may contact. | Met | Outbound destinations are fixed by settings (`config/settings.py:249`, `config/settings.py:223`, `config/settings.py:344`, `config/settings.py:492`); no user-supplied destination exists. |
| V13.2.5 | L2 | The server has an allowlist for outbound requests and loads. | Met | Same fixed destinations; the CSP limits browser loads to self and the storage origin (`config/settings.py:453`). |
| V13.3.1 | L2 | A secrets-management solution stores backend secrets. | Not applicable | Operator's infrastructure: the app reads environment variables, which any vault can inject; `docs/HOSTING.md:278` says to keep them in a secrets store. |
| V13.3.2 | L2 | Access to secrets follows least privilege. | Not applicable | Operator's infrastructure (how `.env` or the vault is protected). |
| V13.4.1 | L1 | No source-control metadata is deployed. | Met | `.dockerignore:2` excludes `.git`. |
| V13.4.2 | L2 | Debug modes are off in production. | Met | Production is the fail-closed default (`config/settings.py:18`, `config/settings.py:26`); the kit is refused (`config/settings.py:129`); `compose.production.yaml:9`. |
| V13.4.3 | L2 | No directory listings unless intended. | Met | WhiteNoise serves only collected files, without listings (`config/settings.py:175`); user files live in a private bucket. |
| V13.4.4 | L2 | HTTP TRACE is not supported in production. | Met | Nothing echoes a TRACE: gunicorn passes it to Django, and views limit methods (`require_safe` in `apps/core/pages.py:41`, `require_POST` in `apps/files/views.py:69`). |
| V13.4.5 | L2 | Internal docs and monitoring endpoints are not exposed unintentionally. | Met | No Django admin or API docs; `/healthz` returns only `{"ok": true}` (`apps/core/views.py:20`); `/_kit/` is refused in production (`config/settings.py:129`). |

## V14 Data Protection

5 Met, 0 Not applicable, 4 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V14.1.1 | L2 | Sensitive data is identified and classified into protection levels. | Met | `docs/security/controls.md` (Data classification). |
| V14.1.2 | L2 | Each protection level has documented protection requirements. | Met | `docs/security/controls.md` (Data classification): protection per level. |
| V14.2.1 | L1 | Sensitive data never travels in URLs or query strings. | Gap (accepted) | Name searches stay in the query string (`?q=`, `apps/awards/staff_views.py:397`, `apps/applications/behalf_views.py:56`): staff screens, signed in, `no-store`, and dropped from the access log (V16.2.5). Accepted in M13; claim and reset tokens in emailed links are redacted and `no-store`. |
| V14.2.2 | L2 | Sensitive data is not cached in server components. | Met | `Cache-Control: no-store, private` on signed-in and secret pages (`apps/core/middleware.py:22`); `apps/core/tests/test_security_headers.py::test_signed_in_pages_are_no_store`. |
| V14.2.3 | L2 | Sensitive data is not sent to untrusted parties such as trackers. | Met | No analytics or trackers (CSP `default-src 'self'`, `config/settings.py:459`); Sentry events are scrubbed (`apps/core/sentry.py:92`; `apps/core/tests/test_sentry.py::test_init_sentry_never_collects_locals_bodies_or_pii`). |
| V14.2.4 | L2 | Sensitive-data controls (retention, logging, privacy) follow each level. | Met | `docs/security/controls.md` (Data classification) maps each control to its level. |
| V14.3.1 | L1 | Authenticated data is cleared from client storage after the session. | Met | Nothing is stored client-side: htmx `historyCacheSize:0` (`templates/base.html:8`), no Web Storage in `frontend/src/`, and signed-in pages are `no-store`. |
| V14.3.2 | L2 | Anti-caching headers (no-store) keep sensitive data out of browsers. | Met | `apps/core/middleware.py:22`; `apps/core/tests/test_security_headers.py::test_secret_route_is_no_store_when_anonymous`. |
| V14.3.3 | L2 | Browser storage holds no sensitive data except session tokens. | Met | No `localStorage`/`sessionStorage`/IndexedDB in `frontend/src/`; htmx history cache off (`templates/base.html:8`). |

## V15 Secure Coding and Architecture

10 Met, 1 Not applicable, 2 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V15.1.1 | L1 | Docs define remediation time frames for vulnerable components. | Met | `SECURITY.md` (Fix targets): critical 7 days, high 30 days, others with the next release. |
| V15.1.2 | L2 | An inventory (SBOM) of third-party components from trusted sources. | Met | `uv.lock` and `frontend/package-lock.json` pin every component from PyPI and npm; CI installs only from them (`.github/workflows/ci.yml:51`). |
| V15.1.3 | L2 | Docs identify resource-heavy functions and how to protect them. | Met | `docs/design/2026-10-11-scholarsync-design.md` §7: exports built in the request at a few thousand rows (line 694), import limits (line 459), photo pixel cap. |
| V15.2.1 | L1 | Components stay within the documented remediation time frames. | Met | Dependabot (`.github/dependabot.yml`) and a weekly CI audit (`.github/workflows/ci.yml` schedule); `tests/test_asvs_gaps.py::test_dependencies_are_watched`. Open at review time: a high advisory in picomatch (build tooling only, no patched version yet), fixed when upstream publishes, per `SECURITY.md`. |
| V15.2.2 | L2 | Defences protect resource-heavy functions from availability loss. | Met | Import caps (`apps/awards/tabular.py:21`), photo pixel cap and decompression-bomb guard (`apps/files/services.py:196`), upload limits (`apps/files/policy.py:55`). |
| V15.2.3 | L2 | Production has no test code, samples or dev features exposed. | Met | The demo is inactive in production and `check --deploy` fails while it exists (`config/settings.py:166`; `apps/core/tests/test_checks.py::test_deploy_check_follows_the_demo_folder`); the kit is refused; `tests/e2e` is not in the image (`.dockerignore:25`). |
| V15.3.1 | L1 | Responses return only the required subset of fields. | Met | JSON endpoints return explicit keys (`apps/files/views.py:87`, `apps/files/views.py:111`); exports leave out birth dates (spec §7, line 694). |
| V15.3.2 | L2 | Backend calls to external URLs don't follow redirects unless intended. | Not applicable | The backend calls no URL a user or third party can choose; only the configured storage endpoint and Google's fixed OAuth endpoints. |
| V15.3.3 | L2 | Mass assignment is prevented by limiting fields per action. | Met | Explicit form fields; role forced on signup (`apps/accounts/adapters.py:44`); `apps/accounts/tests/test_signup.py::test_signup_ignores_role_and_staff_fields`. |
| V15.3.4 | L2 | The client IP is taken from trusted proxy fields only. | Met | `ALLAUTH_TRUSTED_PROXY_COUNT` (`config/settings.py:334`) used by `apps/core/audit.py:27`; `docs/HOSTING.md:185`. |
| V15.3.5 | L2 | Variables have the right type; strict comparisons avoid type juggling. | Met | Upload intents are type-checked, booleans refused as sizes (`apps/files/views.py:57`); `apps/files/tests/test_views.py::test_intent_wrong_field_types`. |
| V15.3.6 | L2 | JavaScript avoids prototype pollution. | Met | Strict TypeScript; server JSON is read through an `isRecord` guard and no untrusted object is merged (`frontend/src/upload.ts:98`). |
| V15.3.7 | L2 | Defend against HTTP parameter pollution. | Met | Django keeps `request.GET` and `request.POST` apart and views read one source; the queue keeps only known keys (`apps/applications/staff_views.py:55`). |

## V16 Security Logging and Error Handling

12 Met, 0 Not applicable, 4 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V16.1.1 | L2 | A logging inventory covers layers, events, formats, storage, access, retention. | Met | `docs/security/controls.md` (Logs): the inventory. |
| V16.2.1 | L2 | Each log entry has when, where, who and what. | Met | Every JSON log line carries `request_id` and `user_id` (`apps/core/request_context.py:33`, `apps/core/logging.py`), the response echoes `X-Request-ID`, and the access log prints it. `apps/core/tests/test_request_context.py::test_request_id_echoed_and_logged`, `apps/core/tests/test_request_context.py::test_log_line_has_user_id_after_sign_in`. |
| V16.2.2 | L2 | Log time sources are synced; timestamps are UTC or carry an offset. | Met | UTC ISO timestamps (`apps/core/logging.py:23`); audit `at` is timezone-aware (`USE_TZ`, `config/settings.py:379`). |
| V16.2.3 | L2 | Logs go only to documented destinations. | Met | stdout (`config/settings.py:487`) and optional Sentry (`config/settings.py:492`), both in spec §10. |
| V16.2.4 | L2 | Logs use a common format a processor can read. | Met | One JSON object per line (`apps/core/logging.py:31`); `apps/core/tests/test_logging.py::test_json_formatter_emits_one_json_object`. |
| V16.2.5 | L2 | Sensitive data is logged only as its protection level allows. | Met | Name searches (`?q=`) and secret URLs are redacted from the access log (`apps/core/gunicorn_logging.py`, `tests/test_asvs_gaps.py::test_access_log_redacts_name_searches`); audit data holds ids only. |
| V16.3.1 | L2 | All authentication operations are logged, success and failure. | Met | `apps/accounts/signals.py:42`; `apps/accounts/tests/test_signals.py::test_sign_in_and_out_are_audited`, `apps/accounts/tests/test_signals.py::test_failed_sign_in_is_audited_without_the_email`. |
| V16.3.2 | L2 | Failed authorisation attempts are logged. | Met | Django's `django.request` logger writes every 403 and 404 as a warning through the JSON handler (`config/settings.py:487`); see V16.2.1 for the missing actor. |
| V16.3.3 | L2 | Documented security events and control-bypass attempts are logged. | Met | Sign-ins, password and email events (`apps/accounts/signals.py:15`), file rejections (`apps/files/services.py:269`); rate-limit and validation refusals reach `django.request` as 4xx warnings. |
| V16.3.4 | L2 | Unexpected errors and security control failures are logged. | Met | Unhandled errors log through `django.request` and Sentry (`config/settings.py:492`); storage outages answer 503 and log; worker failures `logger.exception` (`apps/core/management/commands/run_worker.py:42`). |
| V16.4.1 | L2 | Logging encodes data to prevent log injection. | Met | JSON encoding escapes newlines (`apps/core/logging.py:31`). |
| V16.4.2 | L2 | Logs are protected from unauthorised access and modification. | Met | Audit events are append-only (`apps/core/models.py:7`, `apps/core/models.py:53`); the viewer is office- or head-only (`tests/test_permission_matrix.py::test_access`). |
| V16.4.3 | L2 | Logs are sent to a logically separate system. | Not applicable | Operator infrastructure: logs go to stdout for the host to ship off the machine (`docs/HOSTING.md` step 6, Logs); the audit log rides in database backups. |
| V16.5.1 | L2 | Errors return a generic message, no stack traces or secrets. | Met | Custom 400/403/404/500 pages and `DEBUG` off (`templates/500.html`); `apps/core/tests/test_error_pages.py::test_error_pages_use_the_public_layout`. |
| V16.5.2 | L2 | The app stays secure when external resources fail. | Met | Storage outages answer 503 with a sentence (`apps/files/views.py:42`); email goes through a retried outbox (`apps/accounts/tests/test_signup.py::test_signup_survives_smtp_down`); storage timeouts (`apps/files/storage.py:62`). |
| V16.5.3 | L2 | The app fails closed; errors never let a transaction through. | Met | Atomic services roll back; a bad upload is saved as rejected (`apps/files/services.py:265`); `apps/files/tests/test_services.py::test_storage_down_leaves_the_file_pending`. |

## V17 WebRTC

0 Met, 7 Not applicable, 0 Gap.

| ID | Level | Requirement | Status | Evidence |
|---|---|---|---|---|
| V17.1.1 | L2 | TURN servers block reserved IP ranges. | Not applicable | No WebRTC. |
| V17.2.1 | L2 | The DTLS certificate key follows the key policy. | Not applicable | No WebRTC. |
| V17.2.2 | L2 | Media servers use approved DTLS suites and SRTP profiles. | Not applicable | No WebRTC. |
| V17.2.3 | L2 | SRTP authentication is checked at the media server. | Not applicable | No WebRTC. |
| V17.2.4 | L2 | Media servers survive malformed SRTP packets. | Not applicable | No WebRTC. |
| V17.3.1 | L2 | The signalling server rate-limits floods. | Not applicable | No WebRTC. |
| V17.3.2 | L2 | The signalling server survives malformed messages. | Not applicable | No WebRTC. |

## Open gaps

M13 (2026-11-19) closed 13 of the 14 gaps M12 left; the maintainer's decisions are recorded in the design spec (`docs/design/2026-10-11-scholarsync-design.md`, revisions 21 to 24). M13's two-factor sign-in brought the V6.5 rows into scope, and V6.5.2 was fixed after M14 (revision 24). One gap stays, accepted:

- **V14.2.1** (accepted): student names travel in the query string of staff name searches (`?q=`). They stay in the staff member's browser history, but the screens are signed-in staff screens sent `no-store`, and the access log drops the parameter (V16.2.5). Sentry drops query strings too. Searches stay GET for bookmarkable filters and HTMX history.
