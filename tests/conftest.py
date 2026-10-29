from contextlib import asynccontextmanager

import pytest
from playwright.async_api import async_playwright

from xhs_mcp.browser import XhsBrowser
from xhs_mcp.config import Settings


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        page.set_default_timeout(1_000)
        yield page
        await browser.close()


@pytest.fixture
async def site(page, monkeypatch, tmp_path):
    state = {"html": "", "status": 200, "urls": []}

    async def route_request(route):
        if route.request.resource_type == "document":
            state["urls"].append(route.request.url)
            await route.fulfill(
                status=state["status"],
                content_type="text/html; charset=utf-8",
                body=state["html"],
            )
        else:
            await route.abort()

    await page.route("**/*", route_request)

    @asynccontextmanager
    async def fixture_page(settings):
        yield page

    monkeypatch.setattr("xhs_mcp.browser.browser_page", fixture_page)
    return XhsBrowser(Settings(tmp_path / "profile")), state
