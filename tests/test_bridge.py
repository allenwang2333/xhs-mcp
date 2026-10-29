import asyncio

import pytest

from xhs_mcp.bridge import HELPER_DIR, PuppeteerError
from xhs_mcp.browser import XhsBrowser, XhsError, browser_page
from xhs_mcp.config import Settings


async def test_missing_node_has_actionable_error(monkeypatch, tmp_path):
    async def missing_node(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing_node)
    with pytest.raises(XhsError, match="Node.js 22.12"):
        await XhsBrowser(Settings(tmp_path / "profile")).search_posts("coffee")


async def test_json_bridge_preserves_chinese_and_newlines(page):
    value = {"text": "京都咖啡\n第二行", "count": 2}
    assert await page.evaluate("value => value", value) == value


async def test_production_bridge_does_not_expose_test_commands(monkeypatch, tmp_path):
    monkeypatch.setattr("xhs_mcp.bridge.HELPER_PATH", HELPER_DIR / "bridge.mjs")
    async with browser_page(Settings(tmp_path / "profile")) as page:
        with pytest.raises(PuppeteerError, match="request"):
            await page._request("set_cookies", {"cookies": []})
        assert await page.evaluate("1 + 1") == 2


async def test_raw_browser_errors_do_not_expose_url_tokens(page):
    with pytest.raises(PuppeteerError) as error:
        await page.evaluate("() => { throw new Error('xsec_token=private-value'); }")
    assert str(error.value) == "request"
    assert "private-value" not in str(error.value)
