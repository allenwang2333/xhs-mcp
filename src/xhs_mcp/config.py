import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    profile_dir: Path
    headless: bool = True
    timeout_ms: int = 30_000
    chrome_path: Path | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        default = Path.home() / ".local" / "share" / "xhs-mcp" / "browser-profile"
        return cls(
            profile_dir=Path(os.environ.get("XHS_PROFILE_DIR", str(default))).expanduser(),
            headless=os.environ.get("XHS_HEADLESS", "true").lower() not in {"false", "0", "no"},
            chrome_path=(
                Path(os.environ["XHS_CHROME_PATH"]).expanduser()
                if os.environ.get("XHS_CHROME_PATH")
                else None
            ),
        )
