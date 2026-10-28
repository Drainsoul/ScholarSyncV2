import pytest
from playwright.sync_api import ConsoleMessage, Page


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
