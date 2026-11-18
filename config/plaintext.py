"""Production refuses unencrypted connections to other machines (spec §10, M13; ASVS V12.3.1).

Loopback, single-label service names (compose's `db`, `mail`) and `host.docker.internal` stay on
the same machine or a private Docker network, so they are exempt; ALLOW_PLAINTEXT_SERVICES=true
exempts everything for a private network the operator trusts."""

from urllib.parse import parse_qs, urlsplit

import dj_email_url

TLS_SSLMODES = {"require", "verify-ca", "verify-full"}
FIX = "or set ALLOW_PLAINTEXT_SERVICES=true on a private network you trust (docs/HOSTING.md)"


def _local(host: str) -> bool:
    host = host.lower().strip("[]")
    return (
        host in {"localhost", "host.docker.internal", "::1"}
        or host.startswith("127.")
        or (bool(host) and "." not in host and ":" not in host)
    )


def plaintext_refusals(
    *, database_url: str, email_url: str, storage_urls: dict[str, str], clamav_host: str = ""
) -> list[str]:
    """One sentence per setting that would send data unencrypted to another machine."""
    refusals: list[str] = []
    database = urlsplit(database_url)
    if database.hostname and not _local(database.hostname):
        mode = parse_qs(database.query).get("sslmode", [""])[0]
        if mode not in TLS_SSLMODES:
            refusals.append(
                f"DATABASE_URL connects to {database.hostname} without TLS. Add "
                f"?sslmode=verify-full (or require), {FIX}."
            )
    email = urlsplit(email_url)
    if email.hostname and not _local(email.hostname):
        # Judge what the URL turns into (submission:// and ?tls=true / ?ssl=true encrypt), not
        # its scheme alone.
        parsed = dj_email_url.parse(email_url)
        smtp = parsed.get("EMAIL_BACKEND") == "django.core.mail.backends.smtp.EmailBackend"
        if smtp and not (parsed["EMAIL_USE_TLS"] or parsed["EMAIL_USE_SSL"]):
            refusals.append(
                f"EMAIL_URL sends mail to {email.hostname} unencrypted. Use submission:// "
                f"(STARTTLS, port 587) or add ?ssl=true for port 465, {FIX}."
            )
    for name, url in storage_urls.items():
        parts = urlsplit(url)
        if parts.scheme == "http" and parts.hostname and not _local(parts.hostname):
            refusals.append(
                f"{name} uses http:// to {parts.hostname}. Use an https:// endpoint, {FIX}."
            )
    # clamd's protocol has no TLS: uploads would cross the network in the clear.
    if clamav_host and not _local(clamav_host):
        refusals.append(
            f"CLAMAV_HOST is {clamav_host}, and files sent to clamd are unencrypted. Run clamd on "
            f"this machine or the app's Docker network (for example CLAMAV_HOST=clamav), {FIX}."
        )
    return refusals
