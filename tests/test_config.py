from pathlib import Path

from xhs_mcp.config import Settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("XHS_PROFILE_DIR", raising=False)
    monkeypatch.delenv("XHS_HEADLESS", raising=False)
    settings = Settings.from_env()
    assert settings.headless
    assert settings.profile_dir == Path.home() / ".local/share/xhs-mcp/browser-profile"


def test_environment_settings(monkeypatch):
    monkeypatch.setenv("XHS_PROFILE_DIR", "~/private-xhs")
    monkeypatch.setenv("XHS_HEADLESS", "false")
    settings = Settings.from_env()
    assert not settings.headless
    assert settings.profile_dir == Path.home() / "private-xhs"
