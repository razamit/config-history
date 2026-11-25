"""Local-history wording: save, restore and version N instead of push, pull and snapshot #N.

Applies to the automatic default config and to the config-history program
name. A backend set up with init under the claude-cfg name keeps the sync
words. The sign-in reminder after a restore shows only for a snapshot taken
on another machine.
"""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import pull_summary
from claude_cfg.cli import app, output
from claude_cfg.command_wording import wording_for
from claude_cfg.default_history import load_or_create_config
from claude_cfg.paths import claude_dir
from claude_cfg.program_name import PROGRAM_NAME_ENV
from tests.sync_helpers import write_files

runner = CliRunner()
CREDENTIALS_LINE = "Credentials are never synced"


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def local_history(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"a": 1}', "CLAUDE.md": "# rules"})
    return load_or_create_config()


@pytest.fixture
def sync_backend(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"a": 1}', "CLAUDE.md": "# rules"})
    cfg = {"storage": "local", "tracked": ["settings.json", "CLAUDE.md", "skills/"],
           "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    return cfg


def invoke(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_wording_choice(monkeypatch, sync_backend):
    local = wording_for({"automatic_default": True, "storage": "local"})
    assert local.local_words and local.history_on_this_machine
    synced = wording_for(sync_backend)
    assert not synced.local_words and not synced.history_on_this_machine
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    plugin = wording_for(sync_backend)
    assert plugin.local_words and not plugin.history_on_this_machine


def test_save_accepts_a_message_starting_with_a_dash(local_history):
    assert "Version 1 saved" in invoke("save", "--", "-starts with a dash")
    assert "-starts with a dash" in invoke("list")


def test_local_history_restore_and_undo_wording(monkeypatch, local_history):
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    invoke("save", "one")
    write_files(claude_dir(), {"skills/new/SKILL.md": "x", "settings.json": '{"a": 2}'})
    preview = invoke("restore", "--point", "1", "--dry-run")
    assert "Version 1, saved " in preview and "Snapshot" not in preview
    assert "`/config-history:restore` removes them if asked to" in preview
    restored = invoke("restore", "--point", "1")
    assert "Version 1 restored" in restored
    assert "`/config-history:restore` removes them if you ask it to" in restored
    assert "Type `/config-history:undo` to revert this restore." in restored
    assert "config-history restore" not in restored and "config-history undo" not in restored
    assert CREDENTIALS_LINE not in restored, "same machine"
    assert "Undid the restore of version 1" in invoke("undo")


def test_local_history_status_has_no_remote_line(local_history):
    invoke("save", "one")
    status = invoke("status")
    assert "Last saved: version 1, just now (" in status
    assert "Remote" not in status and "Last synced" not in status


def test_sync_backend_keeps_the_sync_wording(sync_backend):
    assert "Snapshot #1 pushed" in invoke("push", "one")
    write_files(claude_dir(), {"skills/new/SKILL.md": "x", "settings.json": '{"a": 2}'})
    restored = invoke("pull", "--point", "1")
    assert "Snapshot #1 restored" in restored
    assert "(`pull --exact` removes them)" in restored
    assert "to revert this pull." in restored
    status = invoke("status")
    assert "Last synced: snapshot #1" in status and "Remote latest: snapshot #1" in status


def test_credentials_line_only_for_a_snapshot_from_another_machine(monkeypatch, sync_backend):
    invoke("push", "one")
    monkeypatch.setattr(pull_summary.socket, "gethostname", lambda: "a-different-machine")
    assert CREDENTIALS_LINE in invoke("pull", "--point", "1")


@pytest.mark.parametrize("manifest, expected", [
    ({"machine": "here"}, False), ({"machine": "there"}, True), ({}, True), ({"machine": ""}, True),
])
def test_is_from_other_machine(manifest, expected):
    assert pull_summary.is_from_other_machine(manifest, "here") is expected
