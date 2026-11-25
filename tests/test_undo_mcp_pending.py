"""Undo checks the MCP preflight first, and ``--files-only`` leaves MCP pending."""

import json

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.backup_manager import MANIFEST_NAME, BackupManager
from claude_cfg.cli import app, output
from claude_cfg.errors import McpUndoBlockedError, NothingToUndoError
from claude_cfg.mcp_cli_preflight import CLAUDE_CODE_SESSION_ENV, is_valid_server_name
from claude_cfg.mcp_server_sync import McpServerSyncManager
from claude_cfg.paths import backups_dir, claude_dir
from tests.fake_command_runner import RecordingRunner
from tests.mcp_fixtures import MCP_CFG, remote_server, write_claude_json
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files


@pytest.fixture
def pulled():
    """A pull that changed CLAUDE.md and replaced the ``changed`` server."""
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    write_claude_json({"changed": remote_server("https://snap")})
    core.push("one", MCP_CFG, provider)
    write_claude_json({"changed": remote_server("https://local")})
    write_files(claude_dir(), {"CLAUDE.md": "# edited"})
    core.pull(None, MCP_CFG, provider, command_runner=RecordingRunner())
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"
    return provider


def _manifest() -> dict:
    (folder,) = [p for p in backups_dir().iterdir() if p.is_dir()]
    return json.loads((folder / MANIFEST_NAME).read_text())


def test_failing_preflight_refuses_the_whole_undo(pulled, monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_SESSION_ENV, "1")
    runner = RecordingRunner()
    with pytest.raises(McpUndoBlockedError, match="--files-only"):
        core.undo(command_runner=runner)
    assert runner.calls == []
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"
    assert _manifest()["undone_at"] is None


def test_files_only_leaves_mcp_pending_for_the_next_undo(pulled, monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_SESSION_ENV, "1")
    first = core.undo(command_runner=RecordingRunner(), files_only=True)
    assert first.mcp_left_pending and first.mcp_result is None
    assert (claude_dir() / "CLAUDE.md").read_text() == "# edited"
    assert _manifest()["undone_at"] and _manifest()["mcp_reverted_at"] is None
    with pytest.raises(NothingToUndoError, match="only its MCP server changes"):
        core.undo(command_runner=RecordingRunner(), files_only=True)

    monkeypatch.delenv(CLAUDE_CODE_SESSION_ENV)
    runner = RecordingRunner()
    second = core.undo(command_runner=runner)
    assert second.files_already_undone and second.mcp_result.applied == ["changed"]
    added = [c for c in runner.calls if c.arguments[2] == "add-json"]
    assert json.loads(added[0].stdin_text) == remote_server("https://local")
    assert _manifest()["mcp_reverted_at"]
    with pytest.raises(NothingToUndoError):
        core.undo(command_runner=RecordingRunner())


def test_prune_keeps_a_backup_whose_mcp_part_is_pending(pulled, monkeypatch):
    monkeypatch.setenv(CLAUDE_CODE_SESSION_ENV, "1")
    core.undo(command_runner=RecordingRunner(), files_only=True)
    (backups_dir() / "29991231T000000Z").mkdir()
    (backups_dir() / "29991231T000001Z").mkdir()
    removed = BackupManager(backups_dir()).prune(keep=1)
    assert removed == [backups_dir() / "29991231T000000Z"]
    assert len([p for p in backups_dir().iterdir() if p.is_dir()]) == 2


def test_cli_undo_files_only_says_mcp_is_pending(pulled, monkeypatch):
    cfg_mod.save(MCP_CFG)
    monkeypatch.setattr(output.console, "width", 300)
    monkeypatch.setenv(CLAUDE_CODE_SESSION_ENV, "1")
    runner = RecordingRunner()
    monkeypatch.setattr(core, "build_mcp_manager", lambda command_runner=None: McpServerSyncManager(runner))
    refused = CliRunner().invoke(app, ["undo"])
    assert refused.exit_code == 1 and "undo --files-only" in refused.output
    done = CliRunner().invoke(app, ["undo", "--files-only"])
    assert done.exit_code == 0, done.output
    assert "MCP server changes were not put back" in done.output


@pytest.mark.parametrize("name, valid", [
    ("ok-1", True), ("a.b_c", True), ("abc\n", False), ("abc\nx", False),
    ("--scope", False), ("a b", False), ("", False),
])
def test_server_name_must_match_in_full(name, valid):
    assert is_valid_server_name(name) is valid
