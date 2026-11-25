"""Zero setup: CLAUDE_CFG_HOME, the automatic local history and its permissions."""

import json
import os
import stat
import sys

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app, output
from claude_cfg.config import AUTOMATIC_DEFAULT_KEY, DEFAULT_TRACKED, is_autosave_enabled
from claude_cfg.default_history import build_default_config, load_or_create_config
from claude_cfg.paths import (
    CLAUDE_CFG_HOME_ENV,
    backups_dir,
    claude_dir,
    config_dir,
    config_file,
    history_dir,
    state_file,
)
from tests.sync_helpers import write_files

runner = CliRunner()
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_tool_home_env_moves_every_tool_path(isolated_home, tmp_path, monkeypatch):
    tool_home = tmp_path / "tool-home"
    monkeypatch.setenv(CLAUDE_CFG_HOME_ENV, str(tool_home))
    assert config_dir() == tool_home
    for path in (config_file(), state_file(), backups_dir(), history_dir()):
        assert path.parent == tool_home


def test_relative_tool_home_is_ignored(isolated_home, monkeypatch):
    monkeypatch.setenv(CLAUDE_CFG_HOME_ENV, "relative/folder")
    assert config_dir() == isolated_home / ".claude-cfg"


def test_save_with_tool_home_writes_only_there(isolated_home, tmp_path, monkeypatch):
    tool_home = tmp_path / "tool-home"
    monkeypatch.setenv(CLAUDE_CFG_HOME_ENV, str(tool_home))
    write_files(claude_dir(), {"CLAUDE.md": "# rules"})
    result = runner.invoke(app, ["save", "first"])
    assert result.exit_code == 0, result.output
    assert (tool_home / "config.json").is_file() and (tool_home / "state.json").is_file()
    assert list((tool_home / "history" / "snapshots").iterdir())
    assert not (isolated_home / ".claude-cfg").exists()


def test_default_config_is_written_on_first_use_with_its_marker(isolated_home):
    assert not config_file().exists()
    cfg = load_or_create_config()
    saved = json.loads(config_file().read_text())
    assert saved == cfg == build_default_config()
    assert saved[AUTOMATIC_DEFAULT_KEY] is True
    assert saved["storage"] == "local" and saved["local"]["path"] == str(history_dir())
    assert saved["tracked"] == DEFAULT_TRACKED
    assert saved["encryption"] == {"enabled": False}
    assert saved["mcp_servers"] == {"enabled": False}
    assert saved["autosave"] == {"enabled": True, "keep": 50}
    assert is_autosave_enabled(saved)


def test_existing_config_is_used_as_is(isolated_home):
    chosen = {"storage": "local", "local": {"path": str(isolated_home / "store")}, "tracked": []}
    cfg_mod.save(chosen)
    assert load_or_create_config() == chosen
    assert not is_autosave_enabled(chosen)


@pytest.mark.parametrize("command", [["list"], ["status", "--offline"]])
def test_commands_work_before_any_setup(isolated_home, command):
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output
    assert "init" not in result.output
    assert config_file().exists()


@pytest.mark.parametrize("command", [["diff"], ["restore"], ["undo"]])
def test_commands_with_nothing_saved_explain_without_asking_for_init(isolated_home, command):
    result = runner.invoke(app, command)
    assert result.exit_code == 1
    assert "init" not in result.output and "Config not found" not in result.output


def test_save_then_restore_with_no_setup(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"model": "opus"}'})
    assert runner.invoke(app, ["save", "before"]).exit_code == 0
    write_files(claude_dir(), {"settings.json": '{"model": "sonnet"}'})
    restored = runner.invoke(app, ["restore", "--point", "1"])
    assert restored.exit_code == 0, restored.output
    assert json.loads((claude_dir() / "settings.json").read_text()) == {"model": "opus"}


@POSIX_ONLY
def test_history_folder_and_files_are_owner_only(isolated_home):
    write_files(claude_dir(), {"settings.json": "{}", "skills/demo/SKILL.md": "x"})
    assert runner.invoke(app, ["save", "one"]).exit_code == 0
    assert _mode(config_dir()) == 0o700
    assert _mode(config_file()) == 0o600
    assert _mode(history_dir()) == 0o700
    for path in history_dir().rglob("*"):
        assert _mode(path) == (0o700 if path.is_dir() else 0o600), path


def test_init_over_local_history_mentions_it_and_keeps_it(isolated_home, tmp_path):
    write_files(claude_dir(), {"settings.json": "{}"})
    assert runner.invoke(app, ["save", "auto history"]).exit_code == 0
    kept = sorted(p.name for p in (history_dir() / "snapshots").iterdir())
    store = tmp_path / "chosen"
    answers = ["local", str(store), "n", "n", "n"]
    result = runner.invoke(app, ["init"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert "1 saved version(s) already exists" in result.output
    assert sorted(p.name for p in (history_dir() / "snapshots").iterdir()) == kept
    saved = json.loads(config_file().read_text())
    assert AUTOMATIC_DEFAULT_KEY not in saved and saved["local"]["path"] == str(store)
    assert not is_autosave_enabled(saved)


def test_init_without_history_says_nothing_about_it(isolated_home, tmp_path):
    answers = ["local", str(tmp_path / "chosen"), "n", "n", "n"]
    result = runner.invoke(app, ["init"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert "already exists" not in result.output
