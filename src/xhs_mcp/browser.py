import asyncio
import fcntl
import re
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Route, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .config import Settings
from .extract import PAGE_STATE, POST_DETAIL, SEARCH_CARDS
from .models import Post, SearchPost, SearchResults

BASE_URL = "https://www.xiaohongshu.com"
HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com"}
POST_PATH = re.compile(r"/(?:explore|search_result|discovery/item)/([a-fA-F0-9]{24})/?")


class XhsError(Exception):
    """An actionable error that is safe to show to an MCP client."""


def validate_post_url(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.hostname in HOSTS
            and parts.port in (None, 443)
            and parts.username is None
            and parts.password is None
        )
        match = POST_PATH.fullmatch(parts.path)
    except ValueError:
        valid, match = False, None
    if not valid or match is None:
        raise ValueError(
            "Use a full HTTPS Xiaohongshu post URL from search_posts, not a short/share URL."
        )
    # Search result tokens are needed to open some posts. Do not return unrelated query data.
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query)
            if key in {"xsec_token", "xsec_source"}
        ]
    )
    return match.group(1), urlunsplit(("https", "www.xiaohongshu.com", parts.path, query, ""))


@asynccontextmanager
async def browser_page(settings: Settings):
    """Keep a browser profile private and prevent concurrent profile use across processes."""
    profile = settings.profile_dir.resolve()
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.chmod(0o700)
    with (profile / ".xhs-mcp.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise XhsError(
                "Browser profile is busy. Finish login or the other request, then retry."
            ) from None
        try:
            async with async_playwright() as playwright:
                try:
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile),
                        headless=settings.headless,
                        viewport={"width": 1440, "height": 1000},
                        locale="zh-CN",
                    )
                except PlaywrightError:
                    raise XhsError(
                        "Cannot start Chromium. Run 'uv run playwright install chromium'. "
                        "If another browser uses this profile, close it first."
                    ) from None
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    page.set_default_timeout(settings.timeout_ms)
                    page.set_default_navigation_timeout(settings.timeout_ms)
                    await context.route("**/*", restrict_navigation)
                    yield page
                finally:
                    await context.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def restrict_navigation(route: Route):
    request = route.request
    # Only restrict top-level navigation. Site assets and login frames use other hosts.
    if request.is_navigation_request() and request.frame.parent_frame is None:
        url = urlsplit(request.url)
        if url.scheme == "http" and url.hostname in HOSTS and url.port in (None, 80):
            # The site sometimes uses HTTP redirects. Upgrade without sending an HTTP request.
            secure_url = urlunsplit(("https", url.hostname, url.path, url.query, ""))
            await route.fulfill(status=307, headers={"location": secure_url})
            return
        if url.scheme != "https" or url.hostname not in HOSTS or url.port not in (None, 443):
            await route.abort()
            return
    await route.continue_()


class XhsBrowser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def _page(self):
        async with self._lock:
            try:
                async with browser_page(self.settings) as page:
                    yield page
            except PlaywrightTimeout:
                raise XhsError(
                    "Xiaohongshu did not load in time. Retry, or run 'uv run xhs-mcp login' "
                    "to check login and verification."
                ) from None
            except PlaywrightError:
                raise XhsError(
                    "Browser request failed. Run 'uv run xhs-mcp login' "
                    "to check the site, then retry."
                ) from None

    async def _navigate(self, page: Page, url: str, kind: str) -> str:
        response = await page.goto(url, wait_until="domcontentloaded")
        if response and response.status >= 400:
            raise XhsError(f"Xiaohongshu returned HTTP {response.status}. Try the site manually.")
        handle = await page.wait_for_function(PAGE_STATE, arg=kind)
        state = await handle.json_value()
        await handle.dispose()
        self._check_state(state)
        return state

    @staticmethod
    def _check_state(state: str):
        if state == "restricted":
            raise XhsError(
                "Xiaohongshu blocked access during login activation. "
                "This can be an IP/network restriction. Open 'uv run xhs-mcp login' "
                "and follow the site's instructions."
            )
        if state == "login":
            raise XhsError("Login required. Run 'uv run xhs-mcp login', log in, then retry.")
        if state == "verification":
            raise XhsError(
                "Human verification or a rate limit is active. "
                "Run 'uv run xhs-mcp login' and follow the site instructions."
            )
        if state == "unavailable":
            raise XhsError("This post is unavailable or access is restricted.")

    async def search_posts(self, query: str, limit: int = 10) -> SearchResults:
        query = query.strip()
        if not query or len(query) > 200:
            raise ValueError("query must contain 1 to 200 characters after trimming.")
        if isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20.")
        async with self._page() as page:
            state = await self._navigate(
                page,
                f"{BASE_URL}/search_result?"
                + urlencode({"keyword": query, "source": "web_explore_feed"}),
                "search",
            )
            if state == "empty":
                return SearchResults(query=query, posts=[], has_more=False)
            posts: dict[str, SearchPost] = {}
            for attempt in range(6):
                self._check_state(await page.evaluate(PAGE_STATE, "search"))
                cards = await page.evaluate(SEARCH_CARDS)
                for card in cards:
                    try:
                        post_id, url = validate_post_url(card.pop("url"))
                    except ValueError:
                        continue
                    posts.setdefault(post_id, SearchPost(id=post_id, url=url, **card))
                if len(posts) >= limit or attempt == 5:
                    break
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(0.75)
            if not posts:
                raise XhsError("No readable search cards found. The site layout may have changed.")
            scrollable = await page.evaluate(
                "window.scrollY + window.innerHeight < document.documentElement.scrollHeight - 5"
            )
            return SearchResults(
                query=query,
                posts=list(posts.values())[:limit],
                has_more=len(posts) > limit or scrollable,
                warning=(
                    "Only the first loaded results are returned; has_more is a scroll estimate."
                ),
            )

    async def read_post(self, url: str) -> Post:
        post_id, url = validate_post_url(url)
        async with self._page() as page:
            await self._navigate(page, url, "post")
            detail = await page.evaluate(POST_DETAIL)
            if not detail["title"] and not detail["content"]:
                raise XhsError("No readable post content found. The site layout may have changed.")
            return Post(
                id=post_id,
                url=url,
                **detail,
                warning=(
                    "Visible text and image URLs only; "
                    "comments and video transcription are not included."
                ),
            )


async def login(settings: Settings):
    headed = Settings(profile_dir=settings.profile_dir, headless=False)
    async with browser_page(headed) as page:
        await page.goto(f"{BASE_URL}/explore", wait_until="domcontentloaded")
        print("Log in or finish verification in the browser window.")
        prompt = "When finished, press Enter here to save and close the browser: "
        await asyncio.to_thread(input, prompt)
    print("Browser profile saved. The next tool call will check access.")
