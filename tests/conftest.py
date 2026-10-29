from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from xhs_mcp.browser import XhsBrowser, browser_page
from xhs_mcp.config import Settings

FIXTURE_HELPER = Path(__file__).parent / "puppeteer-fixture.mjs"


@pytest.fixture(autouse=True)
def fixture_helper(monkeypatch):
    monkeypatch.setattr("xhs_mcp.bridge.HELPER_PATH", FIXTURE_HELPER)


@pytest.fixture
async def page(tmp_path):
    async with browser_page(Settings(tmp_path / "fixture-profile", timeout_ms=2_000)) as page:
        yield page


@pytest.fixture
async def site(page, monkeypatch, tmp_path):
    state = {"html": "", "status": 200, "urls": []}

    @asynccontextmanager
    async def fixture_page(settings):
        await page._request("fixture", {"html": state["html"], "status": state["status"]})
        try:
            yield page
        finally:
            state["urls"][:] = await page._request("requests")

    monkeypatch.setattr("xhs_mcp.browser.browser_page", fixture_page)
    return XhsBrowser(Settings(tmp_path / "profile")), state
