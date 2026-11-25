"""What a pull reports: platform names and a session hook the snapshot removed."""

import io
import json
import zipfile

from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, output
from claude_cfg.integration_manager import IntegrationManager
from claude_cfg.paths import claude_dir, detect_target, normalize_platform_name, platform_name
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import store_raw_zip, write_files

CFG = {"storage": "local", "tracked": ["settings.json", "CLAUDE.md"]}


def _zip_from(source_platform: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CLAUDE.md", "x")
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 4, "id": 1, "timestamp": "2026-01-01T00:00:00Z", "message": "m",
            "machine": "box", "source_platform": source_platform, "files": ["CLAUDE.md"],
            "tracked": ["CLAUDE.md"],
        }))
    return buffer.getvalue()


def test_manifest_and_target_use_one_platform_naming():
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "x"})
    core.push("one", CFG, provider)
    result = core.pull(None, CFG, provider)
    assert result["source_platform"] == platform_name() == detect_target().platform


def test_old_windows_manifests_read_as_win32():
    assert normalize_platform_name("windows") == "win32"
    assert normalize_platform_name("Darwin") == "darwin"
    provider = MemoryProvider()
    store_raw_zip(provider, _zip_from("windows"))
    assert core.pull(None, CFG, provider)["source_platform"] == "win32"


def test_pull_that_drops_the_session_hook_says_how_to_keep_it(isolated_home, monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)
    cfg = {**CFG, "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    write_files(claude_dir(), {"CLAUDE.md": "x", "settings.json": "{}"})
    runner = CliRunner()
    assert runner.invoke(app, ["push", "before hook"]).exit_code == 0
    IntegrationManager.for_claude_dir(claude_dir()).install()

    result = runner.invoke(app, ["pull"])
    assert result.exit_code == 0, result.output
    assert "removed the claude-cfg session hook" in result.output
    assert "claude-cfg integrate install" in result.output and "claude-cfg push" in result.output


def test_pull_that_keeps_the_hook_says_nothing_about_it():
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "x", "settings.json": "{}"})
    IntegrationManager.for_claude_dir(claude_dir()).install()
    core.push("with hook", CFG, provider)
    assert core.pull(None, CFG, provider)["session_hook_removed"] is False
