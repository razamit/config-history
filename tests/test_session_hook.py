"""`session-hook start` and `session-hook end`: one JSON line or nothing, always exit 0."""

import json
import os
import subprocess
import sys
import time

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, session_hook_commands
from claude_cfg.default_history import load_or_create_config
from claude_cfg.paths import CLAUDE_CFG_HOME_ENV, CLAUDE_CONFIG_DIR_ENV, claude_dir, config_file
from claude_cfg.program_name import PROGRAM_NAME_ENV
from claude_cfg.providers import get_provider
from claude_cfg.session_hook_manager import SessionHookTimeLimits
from claude_cfg.snapshot_store import SnapshotStore
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, write_files

runner = CliRunner()


def _start():
    result = runner.invoke(app, ["session-hook", "start"])
    assert result.exit_code == 0
    return result.output


def _message(output: str) -> str:
    lines = output.splitlines()
    assert len(lines) == 1, output
    document = json.loads(lines[0])
    assert list(document) == ["systemMessage"]
    return document["systemMessage"]


@pytest.fixture
def default_setup(isolated_home):
    write_files(claude_dir(), {"settings.json": "{}", "CLAUDE.md": "# one"})
    return load_or_create_config()


@pytest.fixture
def remote_cfg(isolated_home):
    """A backend chosen in init: no marker, so auto-save is off."""
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    core.push("one", cfg, get_provider(cfg))
    return cfg


def test_first_start_saves_and_says_so(default_setup):
    message = _message(_start())
    assert message == "claude-cfg: saved version 1, the first version of your settings."


def test_start_after_a_change_names_files_and_the_way_back(default_setup):
    _start()
    write_files(claude_dir(), {"settings.json": '{"model": "opus"}', "skills/demo/SKILL.md": "x"})
    message = _message(_start())
    assert message == (
        "claude-cfg: saved version 2 (2 files changed: settings.json, skills/demo/SKILL.md). "
        "Go back with: claude-cfg restore --point 1"
    )


def test_nothing_to_say_prints_nothing(default_setup):
    _start()
    assert _start() == ""


def test_autosave_off_with_changes_suggests_saving(default_setup):
    _start()
    cfg = cfg_mod.load()
    cfg_mod.set_autosave_enabled(cfg, False)
    cfg_mod.save(cfg)
    write_files(claude_dir(), {"CLAUDE.md": "# two"})
    message = _message(_start())
    assert message == (
        "claude-cfg: 1 file changed since the last saved version (CLAUDE.md). "
        "Save them with: claude-cfg save"
    )
    assert len(SnapshotStore(get_provider(cfg)).list_entries()) == 1


def test_remote_newer_is_reported(remote_cfg, tmp_path):
    other = tmp_path / "other"
    write_files(other, {"CLAUDE.md": "# other"})
    push_from_other_machine(get_provider(remote_cfg), other, ["CLAUDE.md"], "laptop")
    message = _message(_start())
    assert message.startswith("claude-cfg: snapshot #2 from ") and "claude-cfg pull" in message


def test_autosave_waits_while_the_remote_is_newer(remote_cfg, tmp_path):
    cfg_mod.set_autosave_enabled(remote_cfg, True)
    cfg_mod.save(remote_cfg)
    other = tmp_path / "other"
    write_files(other, {"CLAUDE.md": "# other"})
    push_from_other_machine(get_provider(remote_cfg), other, ["CLAUDE.md"], "laptop")
    write_files(claude_dir(), {"CLAUDE.md": "# local edit"})
    lines = _message(_start()).split("\n")
    assert len(lines) == 2
    assert "auto-save is waiting" in lines[0] and "snapshot #2" in lines[1]
    assert len(SnapshotStore(get_provider(remote_cfg)).list_entries()) == 2


def test_configured_backend_does_not_autosave_by_default(remote_cfg):
    write_files(claude_dir(), {"CLAUDE.md": "# changed"})
    assert "Save them with: claude-cfg save" in _message(_start())
    assert len(SnapshotStore(get_provider(remote_cfg)).list_entries()) == 1


@pytest.mark.parametrize("text", ["{not json", "[]", '{"storage": "nope"}'])
def test_broken_config_prints_nothing(isolated_home, text):
    config_file().parent.mkdir(parents=True)
    config_file().write_text(text)
    assert _start() == ""
    assert runner.invoke(app, ["session-hook", "end"]).output == ""


def test_raising_provider_on_a_configured_backend_prints_nothing(remote_cfg, monkeypatch):
    def broken(_cfg):
        raise ConnectionError("backend down")

    monkeypatch.setattr(session_hook_commands, "get_provider", broken)
    assert _start() == ""


def test_raising_provider_for_autosave_is_one_line(default_setup, monkeypatch):
    def broken(_cfg):
        raise ConnectionError("disk \x1b[31mgone\n")

    monkeypatch.setattr(session_hook_commands, "get_provider", broken)
    assert _message(_start()) == "claude-cfg: auto-save failed (disk [31mgone)."


class SlowProvider(MemoryProvider):
    def list_keys(self, prefix: str = "") -> list:
        time.sleep(3)
        return []


def test_slow_backend_is_bounded(remote_cfg, monkeypatch):
    monkeypatch.setattr(session_hook_commands, "get_provider", lambda _cfg: SlowProvider())
    monkeypatch.setattr(session_hook_commands, "TIME_LIMITS", SessionHookTimeLimits(0.2, 0.2, 0.2))
    started = time.monotonic()
    assert _start() == ""
    assert time.monotonic() - started < 2


def test_end_saves_and_prints_nothing(default_setup):
    result = runner.invoke(app, ["session-hook", "end"])
    assert result.exit_code == 0 and result.output == ""
    assert len(SnapshotStore(get_provider(default_setup)).list_entries()) == 1


def test_end_with_no_config_prints_nothing(isolated_home):
    result = runner.invoke(app, ["session-hook", "end"])
    assert result.exit_code == 0 and result.output == ""


def test_program_name_in_notice_and_cli_hint(default_setup, monkeypatch):
    """Inside the plugin the notice names the slash command a person can type;
    a command no slash command covers is something to ask Claude, and the
    automatic local history has no encryption notice."""
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    _start()
    write_files(claude_dir(), {"CLAUDE.md": "# two"})
    assert _message(_start()) == (
        "config-history: saved version 2 (1 file changed: CLAUDE.md). "
        "To go back, type /config-history:restore"
    )
    assert runner.invoke(app, ["config", "autosave", "--disable"]).output.strip() == (
        "Auto-save is off. Ask Claude to turn it on "
        "(it runs `config-history config autosave --enable`)."
    )
    pushed = runner.invoke(app, ["save", "by hand"])
    assert pushed.exit_code == 0 and "not encrypted" not in pushed.output


def test_unsafe_program_name_falls_back(default_setup, monkeypatch):
    monkeypatch.setenv(PROGRAM_NAME_ENV, "evil\nname`rm`")
    assert _message(_start()).startswith("claude-cfg: ")


def test_save_and_restore_are_aliases(default_setup):
    help_text = runner.invoke(app, ["--help"], env={"COLUMNS": "200"}).output
    assert "save" in help_text and "Same as push" in help_text and "Same as pull" in help_text
    # Typer 0.29 prints the argument as [message], older versions as [MESSAGE].
    assert "[OPTIONS] [MESSAGE]" in runner.invoke(app, ["save", "--help"]).output.upper()
    restore_help = runner.invoke(app, ["restore", "--help"]).output
    for option in ("--point", "--key", "--dry-run", "--exact", "--yes"):
        assert option in restore_help
    assert runner.invoke(app, ["save", "first"]).exit_code == 0
    write_files(claude_dir(), {"CLAUDE.md": "# changed"})
    preview = runner.invoke(app, ["restore", "--point", "1", "--dry-run"])
    assert preview.exit_code == 0 and "Dry run" in preview.output


@pytest.mark.skipif(sys.platform == "win32", reason="HOME redirection is POSIX")
def test_module_entry_point_prints_one_json_line(tmp_path):
    """The real ``python -m claude_cfg`` entry, with every path in a temp folder."""
    home, claude, tool = tmp_path / "home", tmp_path / "claude", tmp_path / "tool"
    write_files(claude, {"CLAUDE.md": "# rules"})
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           CLAUDE_CONFIG_DIR_ENV: str(claude), CLAUDE_CFG_HOME_ENV: str(tool)}
    env.pop(PROGRAM_NAME_ENV, None)
    command = [sys.executable, "-m", "claude_cfg", "session-hook"]
    started = subprocess.run(command + ["start"], env=env, capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=60)
    assert started.returncode == 0
    assert _message(started.stdout).startswith("claude-cfg: saved version 1")
    ended = subprocess.run(command + ["end"], env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
    assert ended.returncode == 0 and ended.stdout == ""
    assert (tool / "config.json").is_file() and not (home / ".claude-cfg").exists()
