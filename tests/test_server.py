import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from xhs_mcp.models import Post, SearchResults
from xhs_mcp.server import create_server

ROOT = Path(__file__).resolve().parents[1]


async def test_mcp_tools_call_browser_and_return_structured_results(monkeypatch):
    calls = []

    class FakeBrowser:
        def __init__(self, settings):
            pass

        async def search_posts(self, query, limit):
            calls.append((query, limit))
            return SearchResults(query=query, posts=[], has_more=False)

        async def read_post(self, url):
            calls.append(url)
            return Post(id="a" * 24, url=url, title="A post", content="Post content")

    monkeypatch.setattr("xhs_mcp.server.XhsBrowser", FakeBrowser)
    async with create_connected_server_and_client_session(create_server()) as session:
        tools = (await session.list_tools()).tools
        assert {tool.name for tool in tools} == {"search_posts", "read_post"}
        assert all(tool.annotations.readOnlyHint for tool in tools)
        assert all(not tool.annotations.destructiveHint for tool in tools)
        result = await session.call_tool("search_posts", {"query": "coffee", "limit": 2})
        assert not result.isError
        assert result.structuredContent == {
            "query": "coffee",
            "posts": [],
            "has_more": False,
            "warning": None,
        }
        url = "https://www.xiaohongshu.com/explore/" + "a" * 24
        result = await session.call_tool("read_post", {"url": url})
        assert not result.isError
        assert result.structuredContent["content"] == "Post content"
        assert calls == [("coffee", 2), url]
        invalid = await session.call_tool("search_posts", {"query": "coffee", "limit": 21})
        assert invalid.isError
        assert calls == [("coffee", 2), url]


async def test_real_stdio_handshake_and_invalid_input_does_not_launch_browser(tmp_path):
    profile = tmp_path / "profile"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "xhs_mcp.cli", "serve"],
        cwd=str(ROOT),
        env={**os.environ, "XHS_PROFILE_DIR": str(profile)},
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            info = await session.initialize()
            assert info.serverInfo.name == "xhs-mcp"
            tools = (await session.list_tools()).tools
            assert len(tools) == 2
            assert {tool.name for tool in tools} == {"search_posts", "read_post"}
            assert all(tool.outputSchema is not None for tool in tools)
            for name, arguments in [
                ("search_posts", {"query": "   "}),
                ("search_posts", {"query": "coffee", "limit": 0}),
                ("read_post", {"url": "https://attacker.test/"}),
            ]:
                result = await session.call_tool(name, arguments)
                assert result.isError
    assert not profile.exists()
