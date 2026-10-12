from collections.abc import Mapping

VERCEL_HOST_VARIABLES = ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")


def vercel_hosts(environ: Mapping[str, str]) -> list[str]:
    """Hostnames Vercel assigns to this deployment, in a stable order."""
    return [host for name in VERCEL_HOST_VARIABLES if (host := environ.get(name, ""))]
