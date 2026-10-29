"""Private JSON-lines bridge to puppeteer-core. MCP remains a Python server."""

import asyncio
import json
from pathlib import Path

from .config import Settings

HELPER_DIR = Path(__file__).parent / "puppeteer"
HELPER_PATH = HELPER_DIR / "bridge.mjs"


class PuppeteerError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class PuppeteerPage:
    def __init__(self, process: asyncio.subprocess.Process, timeout_ms: int):
        self.process = process
        self.timeout_ms = timeout_ms

    @classmethod
    async def launch(cls, settings: Settings) -> "PuppeteerPage":
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                str(HELPER_PATH),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=2 * 1024 * 1024,
            )
        except FileNotFoundError:
            raise PuppeteerError("node") from None
        page = cls(process, settings.timeout_ms)
        try:
            await page._request(
                "launch",
                {
                    "profile_dir": str(settings.profile_dir.resolve()),
                    "headless": settings.headless,
                    "timeout_ms": settings.timeout_ms,
                    "chrome_path": str(settings.chrome_path) if settings.chrome_path else None,
                },
            )
        except BaseException:
            await page.close()
            raise
        return page

    async def _request(self, method: str, params: dict | None = None):
        try:
            async with asyncio.timeout(self.timeout_ms / 1000 + 5):
                payload = json.dumps({"method": method, "params": params or {}})
                self.process.stdin.write((payload + "\n").encode())
                await self.process.stdin.drain()
                line = await self.process.stdout.readline()
        except TimeoutError:
            raise PuppeteerError("timeout") from None
        except (BrokenPipeError, ConnectionResetError):
            raise PuppeteerError("request") from None
        try:
            response = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            raise PuppeteerError("request") from None
        if not response.get("ok"):
            raise PuppeteerError(response.get("error", "request"))
        return response["result"]

    async def goto(self, url: str) -> int | None:
        return await self._request("goto", {"url": url})

    async def evaluate(self, source: str, argument=None):
        return await self._request("evaluate", {"source": source, "argument": argument})

    async def wait_for_function(self, source: str, argument=None):
        return await self._request("wait_for_function", {"source": source, "argument": argument})

    async def close(self):
        if self.process.returncode is not None:
            return
        # EOF asks the helper to close Chrome, including an in-flight request.
        self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except TimeoutError:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
