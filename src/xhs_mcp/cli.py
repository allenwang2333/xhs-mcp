import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .bridge import HELPER_DIR
from .browser import XhsError, login
from .config import Settings
from .server import create_server


def main():
    parser = argparse.ArgumentParser(description="Read-only Xiaohongshu browser MCP server")
    parser.add_argument("command", choices=("serve", "login", "setup"), nargs="?", default="serve")
    parser.add_argument("--profile", type=Path, help="Use a dedicated browser profile directory")
    parser.add_argument(
        "--headed", action="store_true", help="Show the browser during MCP requests"
    )
    args = parser.parse_args()
    os.umask(0o077)
    settings = Settings.from_env()
    if args.profile:
        settings = replace(settings, profile_dir=args.profile.expanduser())
    if args.headed:
        settings = replace(settings, headless=False)
    try:
        if args.command == "setup":
            npm = shutil.which("npm")
            if not npm:
                raise XhsError("Install Node.js 22.12+ and npm, then run setup again.")
            subprocess.run(
                [
                    npm,
                    "ci",
                    "--prefix",
                    str(HELPER_DIR),
                    "--omit=dev",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                ],
                check=True,
            )
        elif args.command == "login":
            if not sys.stdin.isatty():
                parser.error("login requires an interactive terminal")
            asyncio.run(login(settings))
        else:
            create_server(settings).run(transport="stdio")
    except (XhsError, KeyboardInterrupt, subprocess.CalledProcessError) as exc:
        if isinstance(exc, XhsError):
            print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
