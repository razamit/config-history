"""New default tracked entries, new exclusions, track-defaults and the push hint."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app, output
from claude_cfg.config import DEFAULT_TRACKED
from claude_cfg.exclusion_filter import is_excluded, is_excluded_folder
from claude_cfg.paths import claude_dir
from claude_cfg.tracked_defaults import merge_missing_defaults, untracked_defaults_on_disk
from claude_cfg.tracked_files import list_tracked_files
from tests.sync_helpers import write_files

runner = CliRunner()
NEW_DEFAULTS = ["keybindings.json", "themes/", "rules/", "output-styles/", "workflows/"]


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def old_install(isolated_home):
    """A config saved by an older init, before the new defaults existed."""
    write_files(claude_dir(), {"CLAUDE.md": "# hi", "keybindings.json": "{}", "themes/dark.json": "{}"})
    cfg = {
        "storage": "local",
        "tracked": ["settings.json", "CLAUDE.md", "commands/", "skills/", "agents/", "plugins/"],
        "local": {"path": str(isolated_home / "store")},
    }
    cfg_mod.save(cfg)
    return cfg


def test_new_defaults_are_tracked():
    for entry in NEW_DEFAULTS:
        assert entry in DEFAULT_TRACKED


def test_claude_managed_folders_are_excluded():
    for path in ("skills/synced/x/SKILL.md", "skills/.trash/old/SKILL.md", "plugins/synced/p.json"):
        assert is_excluded(path)
    for folder in ("skills/synced", "skills/.trash", "plugins/synced", "_external"):
        assert is_excluded_folder(folder)
    assert not is_excluded("skills/mine/SKILL.md")


def test_tracked_walk_skips_managed_folders(tmp_path):
    write_files(tmp_path, {
        "skills/mine/SKILL.md": "m", "skills/synced/x/SKILL.md": "s",
        "skills/.trash/y/SKILL.md": "t", "rules/a.md": "r",
    })
    assert list_tracked_files(["skills/", "rules/"], tmp_path) == ["rules/a.md", "skills/mine/SKILL.md"]


def test_merge_missing_defaults_keeps_order_and_custom_entries():
    merged, added = merge_missing_defaults(["CLAUDE.md", "my-notes/", "themes"])
    assert "themes/" not in added  # "themes" without a slash already covers it
    assert added == [d for d in DEFAULT_TRACKED if d not in ("CLAUDE.md", "themes/")]
    assert merged[:3] == ["CLAUDE.md", "my-notes/", "themes"]


def test_untracked_defaults_on_disk_only_lists_existing(old_install):
    assert untracked_defaults_on_disk(old_install["tracked"], claude_dir()) == ["keybindings.json", "themes/"]


def test_track_defaults_command_merges_and_reports(old_install):
    result = runner.invoke(app, ["config", "track-defaults"])
    assert result.exit_code == 0, result.output
    assert "keybindings.json, themes/, rules/, output-styles/, workflows/" in result.output
    assert cfg_mod.load()["tracked"] == old_install["tracked"] + NEW_DEFAULTS

    again = runner.invoke(app, ["config", "track-defaults"])
    assert "already has every default" in again.output
    assert cfg_mod.load()["tracked"] == old_install["tracked"] + NEW_DEFAULTS


def test_push_hints_at_untracked_defaults(old_install):
    result = runner.invoke(app, ["push", "one"])
    assert result.exit_code == 0, result.output
    assert "Not tracked yet: keybindings.json, themes/" in result.output
    assert "claude-cfg config track-defaults" in result.output

    runner.invoke(app, ["config", "track-defaults"])
    quiet = runner.invoke(app, ["push", "two"])
    assert "Not tracked yet" not in quiet.output
