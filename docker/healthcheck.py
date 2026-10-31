"""Container healthcheck: GET /healthz as the reverse proxy would (stdlib only).

Inside the container the request is plain HTTP to 127.0.0.1, but production answers only its own
host name over HTTPS. So the probe sends the first DJANGO_ALLOWED_HOSTS entry as Host and the
X-Forwarded-Proto header a TLS proxy sets. Nothing is relaxed for real requests.
"""

import os
import urllib.request


def probe_headers() -> dict[str, str]:
    hosts = [h.strip().lstrip(".") for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")]
    host = next((h for h in hosts if h and h != "*"), "127.0.0.1")
    return {"Host": host, "X-Forwarded-Proto": "https"}


if __name__ == "__main__":
    request = urllib.request.Request("http://127.0.0.1:8000/healthz", headers=probe_headers())
    urllib.request.urlopen(request, timeout=4)  # noqa: S310
