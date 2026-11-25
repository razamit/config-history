"""Applying MCP server changes through the command runner, undo, and secrecy."""

import json
import os
import platform

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.backup_manager import MANIFEST_NAME
from claude_cfg.cli import app, output
from claude_cfg.mcp_server_sync import (
    NOT_FOUND_REASON,
    ROLLBACK_FAILED_NOTE,
    ROLLED_BACK_NOTE,
    McpServerSyncManager,
)
from claude_cfg.paths import backups_dir, claude_dir
from tests.conftest import RealCommandRunAttempted
from tests.fake_command_runner import MissingProgramRunner, RecordingRunner
from tests.mcp_fixtures import MCP_CFG, SECRET, remote_server, stdio_server, write_claude_json
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files

ADD = ["mcp", "add-json"]
REMOVE = ["mcp", "remove"]


@pytest.fixture
def provider():
    """Snapshot #1 has keep, changed and added. This machine then has keep,
    a different changed, and mine, and an edited CLAUDE.md."""
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    write_claude_json({
        "keep": stdio_server(), "changed": remote_server("https://snap"), "added": stdio_server("a.js"),
    })
    core.push("one", MCP_CFG, provider)
    write_claude_json({"keep": stdio_server(), "changed": remote_server("https://local"), "mine": remote_server()})
    write_files(claude_dir(), {"CLAUDE.md": "# edited"})
    return provider


def _steps(runner: RecordingRunner) -> list[tuple[str, str]]:
    return [(call.arguments[2], call.arguments[3]) for call in runner.calls]


def test_apply_runs_documented_commands_with_definition_on_stdin_only(provider):
    runner = RecordingRunner()
    result = core.pull(None, MCP_CFG, provider, exact=True, command_runner=runner)
    assert _steps(runner) == [
        ("remove", "mine"), ("remove", "changed"), ("add-json", "changed"), ("add-json", "added"),
    ]
    for call in runner.calls:
        assert call.arguments[0] == "claude" and call.arguments[-2:] == ["--scope", "user"]
        assert SECRET not in " ".join(call.arguments)
    adds = [call for call in runner.calls if call.arguments[2] == "add-json"]
    assert all(call.arguments[4] == "-" for call in adds)
    assert json.loads(adds[0].stdin_text) == remote_server("https://snap")
    assert json.loads(adds[1].stdin_text) == stdio_server("a.js")
    assert result["mcp"]["added"] == ["added"] and result["mcp"]["removed"] == ["mine"]
    assert result["mcp"]["failed"] == {}


def test_failing_runner_keeps_file_restore_and_reports_names(provider):
    runner = RecordingRunner(fail_on={"add-json": 1})
    result = core.pull(None, MCP_CFG, provider, command_runner=runner)
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"
    assert sorted(result["mcp"]["failed"]) == ["added", "changed"]
    reason = result["mcp"]["failed"]["added"]
    assert "exited with status 1" in reason
    assert "stderr" not in reason and SECRET not in reason
    # The replaced server: removed, the new add failed, and putting the old
    # definition back was tried right away (and failed too here).
    changed_calls = [c for c in runner.calls if c.arguments[3] == "changed"]
    assert [c.arguments[2] for c in changed_calls] == ["remove", "add-json", "add-json"]
    assert json.loads(changed_calls[2].stdin_text) == remote_server("https://local")
    assert ROLLBACK_FAILED_NOTE in result["mcp"]["failed"]["changed"]
    assert result["mcp"]["rolled_back"] == []


def test_failed_replace_puts_the_previous_definition_back(provider):
    runner = RecordingRunner(fail_counts={"add-json": 1})
    result = core.pull(None, MCP_CFG, provider, command_runner=runner)
    assert _steps(runner) == [
        ("remove", "changed"), ("add-json", "changed"), ("add-json", "changed"), ("add-json", "added"),
    ]
    assert json.loads(runner.calls[2].stdin_text) == remote_server("https://local")
    assert result["mcp"]["rolled_back"] == ["changed"]
    assert ROLLED_BACK_NOTE in result["mcp"]["failed"]["changed"]
    undo_runner = RecordingRunner()
    core.undo(command_runner=undo_runner)
    assert ("add-json", "changed") not in _steps(undo_runner)


def test_mcp_step_is_skipped_inside_a_claude_code_session(provider, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    runner = RecordingRunner()
    result = core.pull(None, MCP_CFG, provider, command_runner=runner)
    assert runner.calls == []
    assert "normal terminal" in result["mcp"]["skipped_reason"]
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"


@pytest.mark.parametrize("version_output", ["2.1.326 (Claude Code)", "not a version"])
def test_mcp_step_is_skipped_for_an_old_or_unreadable_claude(provider, version_output):
    runner = RecordingRunner(version_output=version_output)
    result = core.pull(None, MCP_CFG, provider, command_runner=runner)
    assert runner.calls == []
    assert "2.1.327" in result["mcp"]["skipped_reason"]


@pytest.mark.parametrize("bad_name", ["-rf", "a b", "x;y", "--scope"])
def test_invalid_server_names_never_reach_a_command_line(bad_name):
    from claude_cfg.mcp_server_plan import McpServerPlan

    runner = RecordingRunner()
    plan = McpServerPlan(exact=False, to_add=[bad_name, "ok"], definitions={bad_name: {}, "ok": {}})
    result = McpServerSyncManager(runner, environ={}).apply(plan)
    assert [c.arguments[3] for c in runner.calls] == ["ok"]
    assert bad_name in result.failed and result.applied == ["ok"]


def test_missing_claude_binary_keeps_file_restore(provider):
    runner = MissingProgramRunner()
    result = core.pull(None, MCP_CFG, provider, command_runner=runner)
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"
    assert result["mcp"]["skipped_reason"] == NOT_FOUND_REASON
    assert result["mcp"]["failed"] == {}
    assert runner.calls == 1


def test_default_runner_is_blocked_in_tests(provider):
    with pytest.raises(RealCommandRunAttempted):
        core.pull(None, MCP_CFG, provider)


def test_backup_manifest_records_previous_definitions_owner_only(provider):
    result = core.pull(None, MCP_CFG, provider, exact=True, command_runner=RecordingRunner())
    manifest_path = backups_dir() / os.path.basename(result["backup_dir"]) / MANIFEST_NAME
    record = json.loads(manifest_path.read_text())["mcp_servers"]
    assert record["added"] == ["added"]
    assert record["replaced"] == {"changed": remote_server("https://local")}
    assert record["removed"] == {"mine": remote_server()}
    if platform.system() != "Windows":
        assert oct(os.stat(manifest_path).st_mode & 0o777) == "0o600"


def test_undo_reverses_mcp_changes(provider):
    core.pull(None, MCP_CFG, provider, exact=True, command_runner=RecordingRunner())
    undo_runner = RecordingRunner()
    result = core.undo(command_runner=undo_runner)
    assert _steps(undo_runner) == [
        ("remove", "added"), ("remove", "changed"), ("add-json", "changed"), ("add-json", "mine"),
    ]
    stdin_by_name = {c.arguments[3]: c.stdin_text for c in undo_runner.calls if c.arguments[2] == "add-json"}
    assert json.loads(stdin_by_name["changed"]) == remote_server("https://local")
    assert json.loads(stdin_by_name["mine"]) == remote_server()
    assert sorted(result.mcp_result.applied) == ["added", "changed", "mine"]
    assert (claude_dir() / "CLAUDE.md").read_text() == "# edited"


def test_undo_skips_adds_that_never_happened(provider):
    core.pull(None, MCP_CFG, provider, command_runner=RecordingRunner(fail_on={"add-json": 1}))
    undo_runner = RecordingRunner()
    core.undo(command_runner=undo_runner)
    assert ("remove", "added") not in _steps(undo_runner)
    assert ("add-json", "changed") in _steps(undo_runner)


def test_pull_with_only_mcp_changes_still_backs_up(provider):
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    result = core.pull(None, MCP_CFG, provider, command_runner=RecordingRunner())
    assert result["backup_dir"] is not None and result["files_restored"] == 0


@pytest.fixture
def cli_with_runner(provider, isolated_home, monkeypatch):
    """The provider's snapshot on a local backend, with a failing runner injected."""
    store = isolated_home / "store"
    cfg = {**MCP_CFG, "local": {"path": str(store)}}
    store_snapshots = store / "snapshots"
    store_snapshots.mkdir(parents=True)
    for key, blob in provider._store.items():
        (store / key).write_bytes(blob)
    cfg_mod.save(cfg)
    monkeypatch.setattr(output.console, "width", 300)
    runner = RecordingRunner(fail_on={"add-json": 1})
    monkeypatch.setattr(core, "build_mcp_manager", lambda command_runner=None: McpServerSyncManager(runner))
    return runner


def test_no_secret_in_any_cli_output(cli_with_runner):
    cli = CliRunner()
    outputs = [
        cli.invoke(app, ["pull", "--dry-run", "--exact"]),
        cli.invoke(app, ["diff"]),
        cli.invoke(app, ["pull", "--exact", "--yes"]),
        cli.invoke(app, ["status", "--offline"]),
        cli.invoke(app, ["undo"]),
        cli.invoke(app, ["config", "show"]),
    ]
    for result in outputs:
        assert result.exit_code == 0, result.output
        assert SECRET not in result.output
        assert "Bearer" not in result.output and "API_KEY" not in result.output
    dry_run, diff, pull = (r.output for r in outputs[:3])
    assert "+ added" in dry_run and "~ changed" in dry_run and "- mine" in dry_run
    assert "mine" in diff and "Servers only on this machine" in diff
    assert "changed: `claude mcp add-json` exited with status 1" in pull
    assert "MCP server change(s) were not applied. The files were put back" in outputs[4].output


def test_exact_pull_asks_before_removing_servers(cli_with_runner, monkeypatch):
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    from claude_cfg.cli import restore_commands

    monkeypatch.setattr(restore_commands, "stdin_is_interactive", lambda: False)
    result = CliRunner().invoke(app, ["pull", "--exact"])
    assert result.exit_code == 1
    assert "1 MCP server(s)" in result.output and cli_with_runner.calls == []
