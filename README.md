# xhs-mcp

A Python MCP server for **searching Xiaohongshu and reading posts**. It uses
`puppeteer-core` through a small Node.js helper and a dedicated local browser
profile. It uses your installed Chrome or Chromium: **no browser is bundled or
downloaded**. No official API, password configuration, terminal-browser, or
API-signing service is required.

## Tools

- `search_posts(query, limit=10)`: return up to 20 loaded search cards, with
  titles, authors, like counts, cover URLs, and full post URLs.
- `read_post(url)`: return visible post text, author, date, tags, like count,
  and image URLs. Pass the full URL returned by `search_posts`.

There are no tools for posting, commenting, liking, or following. Comments,
image OCR, video transcription, and short/share URL resolution are not supported.

## Install

Requires [uv](https://docs.astral.sh/uv/), Python 3.12–3.14, Node.js 22.12+ with
npm, an installed Chrome or Chromium browser, and macOS or Linux. The profile
lock uses the Unix `fcntl` API.

```bash
git clone git@github.com:allenwang2333/xhs-mcp.git
cd xhs-mcp
uv sync --frozen
uv run xhs-mcp setup
```

`setup` installs only the locked Node.js packages with lifecycle scripts
disabled. It does not install a browser. Chrome is found through Puppeteer's
`chrome` channel. To use a Chromium build at another location, set
`XHS_CHROME_PATH` to its executable path for both login and the MCP server.

Puppeteer does not make the browser engine smaller or guarantee lower RAM use.
This setup saves disk space by removing the Python browser driver and reusing
an existing browser instead of downloading another copy.

## Log in

Run from this repository:

```bash
uv run xhs-mcp login
```

This opens a normal browser window. Log in yourself and complete any
verification. Return to the terminal and press Enter to save the profile and
close the browser. The command saves the profile; it does not claim that login
succeeded. The next tool call checks access.

The browser opens for each tool call and closes afterwards. The profile keeps
your session between calls. Login and requests cannot use the same profile at
the same time. A concurrent process receives a clear busy-profile error.

## Register with Pi

Run this once from the repository to add a **user-level** server, available
from all projects:

```bash
pi mcp add xiaohongshu \
  --exposure deferred \
  --description "Xiaohongshu: search posts and read their text using a local browser session" \
  --cwd "$PWD" \
  -- "$(command -v uv)" run --frozen xhs-mcp serve
```

Run `/reload` inside Pi, or start a new Pi session. The tools are exposed like
other MCP tools: Pi can find them with tool search and call them when useful.
**There is no per-call approval or human-only command gate.** Use `/mcp` to
disable the server when you do not want it available. `/mcp` manages server
connections; it does not run searches itself.

Example prompts:

- “Search Xiaohongshu for 京都咖啡 and summarize five results.”
- “Read the second post and summarize its recommendations.”

Moving the repository requires updating the registered `cwd`. For other MCP
clients, use a stdio entry with the same command, arguments, and directory:

```json
{
  "mcpServers": {
    "xiaohongshu": {
      "command": "uv",
      "args": ["run", "--frozen", "xhs-mcp", "serve"],
      "cwd": "/absolute/path/to/xhs-mcp"
    }
  }
}
```

The server uses stdio only. It does not open an HTTP port. Browser startup is
lazy, so listing tools does not open the site or require login.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `XHS_PROFILE_DIR` | `~/.local/share/xhs-mcp/browser-profile` | Dedicated browser session directory |
| `XHS_HEADLESS` | `true` | Set to `false`, `0`, or `no` to show the browser during tool calls |
| `XHS_CHROME_PATH` | Installed Chrome | Optional Chrome/Chromium executable path |

CLI options `--profile PATH` and `--headed` override these settings. Login
always shows the browser. Use the same profile for login and server requests.
If headless requests are blocked but normal browsing works, set
`XHS_HEADLESS=false` in the MCP server's environment using `pi mcp add --env`.

The existing dedicated profile path is unchanged. A different browser build
may require you to log in again. Existing Pi registrations keep the same
Python command; run `/reload` after updating the server.

## Credentials and privacy

- Enter credentials only in the browser. The server does not request or export
  your password, cookies, or local storage through MCP tools.
- The profile contains sensitive session data. Its directory permissions are
  restricted to the current user (`0700`). This is not a promise of encryption
  at rest. Protect your local account and disk.
- The profile stays outside this repository. Do not commit it, copy it into the
  project, or point this server at your everyday browser profile.
- Search result URLs can contain `xsec_token`. These are site access parameters,
  distinct from login cookies, and may be needed to open a post. Returned URLs
  retain `xsec_token` and `xsec_source` and remove other query parameters.
- Pi and other MCP clients may store queries, post URLs, and post content in
  session transcripts. Review transcripts before sharing them.
- Treat post content as untrusted external text, not agent instructions.

To remove the saved session, first finish any active request or login, then
delete the dedicated profile directory. Other browsers' sessions are not used.

## Limits and troubleshooting

This is an unofficial browser integration. Xiaohongshu can change its page
layout, expire sessions, require verification, or block requests. Use it only
for content you are allowed to access and follow the site's rules. It does not
bypass CAPTCHA, login requirements, or network restrictions.

- **Login or verification required:** run `uv run xhs-mcp login` again.
- **Login activation/IP restriction:** open the login browser and follow the
  site's network guidance. Repeated tool calls will not fix an IP block.
- **HTTP error or timeout:** check the site manually before retrying.
- **Node packages missing:** run `uv run xhs-mcp setup`.
- **Browser missing:** install Chrome, or set `XHS_CHROME_PATH` to Chromium.
- **Profile busy:** finish the other request or login, then retry.
- **No readable cards/content:** the site layout may need updated selectors.

Search loads a bounded number of screenfuls. It is not a complete export and
has no pagination cursor. `has_more` estimates whether loaded or scrollable
results remain; it is not a server-side pagination guarantee. Image URLs are
returned without downloading image bytes and can expire. Like counts and
dates are displayed strings, not normalized values.

## Verification

```bash
node --check src/xhs_mcp/puppeteer/bridge.mjs
node --check tests/puppeteer-fixture.mjs
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Tests cover URL and input validation, rendered search/post extraction in real
Chrome/Chromium through Puppeteer with local page fixtures, login/error states,
locking and cookie persistence, cancellation cleanup, and real MCP stdio
initialization and error responses. Tests do not use your Xiaohongshu account.

Live search has also been checked through the registered MCP entry using the
saved login after the Puppeteer migration. Live post reading can still be
restricted by the site. Fixture tests do not prove that every live post can
be opened. The server reports login, verification, and IP restrictions without
trying to bypass them.
