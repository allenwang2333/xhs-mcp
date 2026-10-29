import asyncio
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import pytest

from xhs_mcp.browser import XhsBrowser, XhsError, browser_page, validate_post_url
from xhs_mcp.config import Settings
from xhs_mcp.extract import PAGE_STATE

POST_ID = "64a123456789abcdef012345"
POST_URL = f"https://www.xiaohongshu.com/explore/{POST_ID}"


@pytest.mark.parametrize("path", ["explore", "search_result", "discovery/item"])
def test_valid_post_urls_keep_only_access_queries(path):
    post_id, url = validate_post_url(
        f"https://xiaohongshu.com/{path}/{POST_ID}?xsec_token=a%2Bb&tracking=secret"
        "&xsec_source=pc_search#ignored"
    )
    assert post_id == POST_ID
    assert url == (
        f"https://www.xiaohongshu.com/{path}/{POST_ID}?xsec_token=a%2Bb&xsec_source=pc_search"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.xiaohongshu.com/explore/" + POST_ID,
        "https://www.xiaohongshu.com.attacker.test/explore/" + POST_ID,
        "https://attacker.test/explore/" + POST_ID,
        "https://user:password@www.xiaohongshu.com/explore/" + POST_ID,
        "https://www.xiaohongshu.com:8080/explore/" + POST_ID,
        "https://www.xiaohongshu.com:bad/explore/" + POST_ID,
        "https://[invalid/",
        "file:///etc/passwd",
        "https://xhslink.com/abc",
        "https://www.xiaohongshu.com/user/profile/" + POST_ID,
        "https://www.xiaohongshu.com/explore/not-a-post-id",
        POST_URL + "/extra",
    ],
)
def test_reject_invalid_post_urls(url):
    with pytest.raises(ValueError, match="full HTTPS"):
        validate_post_url(url)


@pytest.mark.parametrize(
    ("query", "limit"), [(" ", 10), ("x" * 201, 10), ("x", 0), ("x", 21), ("x", True)]
)
async def test_invalid_search_does_not_open_browser(tmp_path, query, limit):
    profile = tmp_path / "profile"
    with pytest.raises(ValueError):
        await XhsBrowser(Settings(profile)).search_posts(query, limit)
    assert not profile.exists()


def card(post_id=POST_ID, host="www.xiaohongshu.com"):
    return f"""<section class="note-item">
        <a class="cover" href="https://{host}/search_result/{post_id}?xsec_token=example">
            <img src="https://images.test/cover.jpg">
        </a>
        <a class="title"><span>京都咖啡</span></a>
        <div class="author"><span class="name">作者</span></div>
        <div class="like-wrapper"><span class="count">1.2万</span></div>
    </section>"""


async def test_search_extracts_deduplicates_limits_and_encodes_query(site):
    browser, state = site
    state["html"] = card() + card() + card(host="attacker.test") + card("a" * 24)
    result = await browser.search_posts("  京都 & 咖啡  ", limit=1)
    assert result.query == "京都 & 咖啡"
    assert len(result.posts) == 1
    assert result.posts[0].title == "京都咖啡"
    assert result.posts[0].author == "作者"
    assert result.posts[0].likes == "1.2万"
    assert result.posts[0].url.endswith("?xsec_token=example")
    assert result.has_more
    assert parse_qs(urlsplit(state["urls"][0]).query)["keyword"] == ["京都 & 咖啡"]


async def test_search_deduplicates_across_scrolls(site, monkeypatch):
    browser, state = site
    state["html"] = card() + card()

    async def no_delay(seconds):
        return None

    monkeypatch.setattr("xhs_mcp.browser.asyncio.sleep", no_delay)
    result = await browser.search_posts("coffee", limit=2)
    assert len(result.posts) == 1
    assert not result.has_more


async def test_empty_search(site):
    browser, state = site
    state["html"] = "<p>暂无搜索结果</p>"
    result = await browser.search_posts("nothing")
    assert result.posts == []
    assert not result.has_more


async def test_post_extracts_text_images_and_tags(site):
    browser, state = site
    state["html"] = """<div class="note-container">
      <div class="author-container"><span class="username">小红</span></div>
      <h1 id="detail-title">京都旅行</h1>
      <div id="detail-desc">咖啡很好喝。<span class="tag">#京都</span></div>
      <div class="bottom-container"><span class="date">昨天</span></div>
      <div class="interact-container"><div class="like-wrapper">
        <span class="count">20</span></div></div>
      <div class="swiper-slide"><img src="https://images.test/one.jpg"></div>
      <div class="swiper-slide"><img src="https://images.test/one.jpg"></div>
    </div>"""
    result = await browser.read_post(POST_URL + "?xsec_token=example&tracking=remove")
    assert result.id == POST_ID
    assert result.title == "京都旅行"
    assert result.content == "咖啡很好喝。#京都"
    assert result.author == "小红"
    assert result.date == "昨天"
    assert result.likes == "20"
    assert result.tags == ["#京都"]
    assert result.images == ["https://images.test/one.jpg"]
    assert "tracking" not in result.url


@pytest.mark.parametrize(
    ("html", "error"),
    [
        ('<div class="login-container">登录</div>', "Login required"),
        ('<div class="captcha-container">验证码</div>', "Human verification"),
        ("<p>访问过于频繁</p>", "Human verification"),
        ("<p>笔记已删除</p>", "unavailable"),
        (
            '<script>history.replaceState({}, "", '
            '"/website-login/error?error_code=300012")</script>',
            "IP/network restriction",
        ),
    ],
)
async def test_human_action_errors(site, html, error):
    browser, state = site
    state["html"] = html
    with pytest.raises(XhsError, match=error):
        await browser.read_post(POST_URL)


async def test_http_error(site):
    browser, state = site
    state["status"] = 429
    with pytest.raises(XhsError, match="HTTP 429"):
        await browser.search_posts("coffee")


async def test_changed_layout_times_out_with_actionable_error(site):
    browser, state = site
    state["html"] = "<p>unknown page layout</p>"
    with pytest.raises(XhsError, match="did not load in time"):
        await browser.read_post(POST_URL)


async def test_normal_post_text_does_not_trigger_verification(page):
    await page._request(
        "set_content",
        {
            "html": '<div class="login-container" style="display:none">登录</div>'
            '<h1 id="detail-title">关于安全验证和笔记已删除</h1>'
        },
    )
    assert await page.evaluate(PAGE_STATE, "post") == "ready"


async def test_cancellation_releases_operation_lock(monkeypatch, tmp_path):
    closed = []

    @asynccontextmanager
    async def fake_page(settings):
        try:
            yield None
        finally:
            closed.append(True)

    monkeypatch.setattr("xhs_mcp.browser.browser_page", fake_page)
    browser = XhsBrowser(Settings(tmp_path))
    with pytest.raises(asyncio.CancelledError):
        async with browser._page():
            raise asyncio.CancelledError
    assert closed == [True]
    assert not browser._lock.locked()


async def test_profile_lock_and_cookie_persistence(tmp_path):
    settings = Settings(tmp_path / "profile")
    async with browser_page(settings) as page:
        await page._request(
            "set_cookies",
            {
                "cookies": [
                    {
                        "name": "test_session",
                        "value": "fixture-only",
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                        "expires": 2_000_000_000,
                    }
                ]
            },
        )
        with pytest.raises(XhsError, match="profile is busy"):
            async with browser_page(settings):
                pytest.fail("Concurrent profile use must fail")
    assert settings.profile_dir.stat().st_mode & 0o777 == 0o700
    async with browser_page(settings) as page:
        cookies = await page._request("cookies")
        assert any(c["name"] == "test_session" and c["value"] == "fixture-only" for c in cookies)


async def test_external_top_level_navigation_is_blocked(tmp_path):
    from xhs_mcp.bridge import PuppeteerError

    async with browser_page(Settings(tmp_path / "profile")) as page:
        with pytest.raises(PuppeteerError, match="request"):
            await page.goto("https://example.com")


async def test_same_site_http_redirect_upgrades_without_http_network_request(tmp_path):
    async with browser_page(Settings(tmp_path / "profile")) as page:
        await page._request("fixture", {"html": "<p>Fixture</p>", "status": 200})
        await page.goto("http://www.xiaohongshu.com/website-login/error?error_code=300012")
        assert await page.evaluate("location.href") == (
            "https://www.xiaohongshu.com/website-login/error?error_code=300012"
        )
        assert await page.evaluate(PAGE_STATE, "search") == "restricted"


async def test_cancelled_request_closes_helper_and_releases_profile(tmp_path):
    settings = Settings(tmp_path / "profile")
    started = asyncio.Event()
    processes = []

    async def request():
        async with browser_page(settings) as page:
            processes.append(page.process)
            started.set()
            await page.wait_for_function("() => false")

    task = asyncio.create_task(request())
    await asyncio.wait_for(started.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].returncode is not None
    async with browser_page(settings):
        pass


async def test_missing_chrome_has_actionable_error(tmp_path):
    browser = XhsBrowser(Settings(tmp_path / "profile", chrome_path=tmp_path / "missing-chrome"))
    with pytest.raises(XhsError, match="XHS_CHROME_PATH"):
        await browser.search_posts("coffee")
