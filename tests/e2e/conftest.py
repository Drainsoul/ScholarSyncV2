from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from botocore.config import Config
from moto.server import ThreadedMotoServer
from playwright.sync_api import ConsoleMessage, Page

MOTO_PORT = 9199  # config.e2e_settings points S3_ENDPOINT_URL here


@pytest.fixture(autouse=True)
def _e2e_db(transactional_db):
    """The live server answers from another thread, so tests need a transactional database."""


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """Console errors and uncaught exceptions (CSP violations too). Request before page.goto()."""
    errors: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


@pytest.fixture(scope="session")
def e2e_storage(live_server) -> Iterator[str]:
    """A moto S3 server on the port config.e2e_settings names, with the "e2e" bucket.

    The browser PUTs to it from the live server's origin, so the bucket allows that origin (CORS).
    Only upload tests request this fixture.
    """
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=MOTO_PORT)
    server.start()
    endpoint = f"http://127.0.0.1:{MOTO_PORT}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # noqa: S106
        config=Config(s3={"addressing_style": "path"}),
    )
    client.create_bucket(Bucket="e2e")
    client.put_bucket_cors(
        Bucket="e2e",
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": [live_server.url],
                    "AllowedMethods": ["GET", "PUT"],
                    "AllowedHeaders": ["*"],
                    "MaxAgeSeconds": 600,
                }
            ]
        },
    )
    yield endpoint
    server.stop()


AXE_SOURCE = (
    Path(__file__).resolve().parents[2] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
)
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


@pytest.fixture(scope="session")
def axe_source() -> str:
    """axe-core (a pinned dev dependency), read once. Pages are checked in a `bypass_csp`
    context: the injected checker is a test script; the app's policy stays enforced elsewhere."""
    return AXE_SOURCE.read_text(encoding="utf-8")


def axe_violations(page: Page, source: str) -> list[dict[str, str]]:
    """WCAG 2.2 A/AA violations on the page: id, impact, the first target and the help text."""
    page.evaluate(source)
    violations: list[dict[str, str]] = page.evaluate(
        """async (tags) => {
            const result = await axe.run(document, {runOnly: {type: "tag", values: tags}});
            return result.violations.map((v) => ({
                id: v.id,
                impact: v.impact || "",
                target: v.nodes.length ? v.nodes[0].target.join(" ") : "",
                help: v.help,
            }));
        }""",
        AXE_TAGS,
    )
    return violations
