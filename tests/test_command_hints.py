"""Hints name what the user can type.

Inside the plugin (program name ``config-history``) the command is on the
PATH of Claude's shell only, so hints name slash commands. Under the
``claude-cfg`` name they keep the shell commands.
"""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.autosave_manager import AutoSaveOutcome, AutoSaveResult
from claude_cfg.cli import app, output
from claude_cfg.cli.autosave_commands import autosave_state_text, autosave_summary
from claude_cfg.cli.mcp_prompts import print_mcp_sync_state
from claude_cfg.cli.status_output import next_step_text
from claude_cfg.command_wording import wording_for
from claude_cfg.default_history import load_or_create_config
from claude_cfg.paths import claude_dir
from claude_cfg.passphrase import mismatch_message, unavailable_message
from claude_cfg.program_name import PROGRAM_NAME_ENV, command_hint, shell_command_hint
from claude_cfg.session_hook_lines import autosave_line
from claude_cfg.snapshot_selection import no_snapshots_message
from claude_cfg.sync_status import SuggestedAction
from claude_cfg.undo_manager import files_only_undo_text
from tests.sync_helpers import write_files

runner = CliRunner()
SAVED = AutoSaveResult(
    AutoSaveOutcome.SAVED, changed_paths=["settings.json"], snapshot_id=2, previous_id=1
)


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def plugin_name(monkeypatch):
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")


@pytest.fixture
def local_history(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"a": 1}', "CLAUDE.md": "# rules"})
    return load_or_create_config()


def invoke(*args, expected_exit=0):
    result = runner.invoke(app, list(args))
    assert result.exit_code == expected_exit, result.output
    return result.output


@pytest.mark.parametrize("arguments, expected", [
    ("restore --point 1", "/config-history:restore"),
    ("pull --exact", "/config-history:restore"),
    ("undo", "/config-history:undo"),
    ("undo --force", "config-history undo --force"),
    ("list", "/config-history:history"),
    ("history --limit 5", "/config-history:history"),
    ("diff", "/config-history:history"),
    ("save", "/config-history:history save"),
    ("config encrypt", "config-history config encrypt"),
])
def test_plugin_hints_name_slash_commands(plugin_name, arguments, expected):
    assert command_hint(arguments) == expected


@pytest.mark.parametrize("arguments", ["restore --point 1", "undo", "list", "save"])
def test_cli_hints_keep_shell_commands(arguments):
    assert command_hint(arguments) == "claude-cfg " + arguments
    assert shell_command_hint(arguments) == "claude-cfg " + arguments


def test_notice_under_each_name(monkeypatch):
    assert autosave_line(SAVED, wording_for(None)) == (
        "claude-cfg: saved version 2 (1 file changed: settings.json). "
        "Go back with: claude-cfg restore --point 1"
    )
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    assert autosave_line(SAVED, wording_for(None)) == (
        "config-history: saved version 2 (1 file changed: settings.json). "
        "To go back, type /config-history:restore"
    )


def _restore_then_undo():
    invoke("save", "one")
    write_files(claude_dir(), {"settings.json": '{"a": 2}', "skills/new/SKILL.md": "x"})
    preview = invoke("restore", "--point", "1", "--dry-run")
    restored = invoke("restore", "--point", "1")
    undone = invoke("undo")
    return preview, restored, undone


def test_restore_and_undo_output_in_the_plugin(plugin_name, local_history):
    preview, restored, undone = _restore_then_undo()
    assert "`/config-history:restore` removes them if asked to" in preview
    assert "Type `/config-history:undo` to revert this restore." in restored
    assert "Undid the restore of version 1 from just now (" in undone
    for text in (preview, restored, undone):
        assert "config-history restore" not in text and "config-history undo" not in text


def test_restore_and_undo_output_under_claude_cfg(local_history):
    preview, restored, undone = _restore_then_undo()
    assert "`claude-cfg restore --exact` would remove them" in preview
    assert "Run `claude-cfg undo` to revert this restore." in restored
    assert "/config-history:" not in preview + restored + undone


def _undo_after_an_edit():
    invoke("save", "one")
    write_files(claude_dir(), {"settings.json": '{"a": 2}'})
    invoke("restore", "--point", "1")
    write_files(claude_dir(), {"settings.json": '{"a": 3}'})
    return " ".join(invoke("undo", expected_exit=1).split())


def test_undo_conflict_in_the_plugin_is_a_request_to_claude(plugin_name, local_history):
    refused = _undo_after_an_edit()
    assert ("Ask Claude to undo it anyway and replace those edits "
            "(it runs `config-history undo --force`).") in refused
    assert "Run `config-history" not in refused


def test_undo_conflict_under_claude_cfg_keeps_the_shell_command(local_history):
    assert "Run `claude-cfg undo --force` to revert them anyway." in _undo_after_an_edit()


def test_status_next_step_under_each_name(monkeypatch, local_history):
    shell = next_step_text(SuggestedAction.PULL, wording_for(local_history))
    assert shell == "Next: a newer version exists. Run `claude-cfg restore` to return to it."
    shell_save = next_step_text(SuggestedAction.PUSH, wording_for(local_history))
    assert shell_save == "Next: run `claude-cfg save` to save this machine's changes."
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    slash = next_step_text(SuggestedAction.PULL, wording_for(local_history))
    assert slash == "Next: a newer version exists. Type `/config-history:restore` to return to it."
    saving = next_step_text(SuggestedAction.PUSH, wording_for(local_history))
    assert saving == "Next: to keep this machine's changes, ask Claude to save a version now."


def test_status_command_in_the_plugin(plugin_name, local_history):
    invoke("save", "one")
    write_files(claude_dir(), {"settings.json": '{"a": 2}'})
    status = invoke("status")
    assert "Next: to keep this machine's changes, ask Claude to save a version now." in status
    assert "config-history save" not in status and "history save" not in status


@pytest.fixture
def backend_from_init(isolated_home, tmp_path):
    """A local backend set up with ``init``, not the automatic history."""
    write_files(claude_dir(), {"CLAUDE.md": "# rules"})
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(tmp_path / "store")}}
    cfg_mod.save(cfg)
    return cfg


def one_line(text):
    return " ".join(text.split())


@pytest.mark.parametrize("use_plugin", [False, True])
def test_no_encryption_notice_for_the_automatic_local_history(monkeypatch, local_history,
                                                               use_plugin):
    if use_plugin:
        monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    saved = invoke("save", "by hand")
    assert "not encrypted" not in saved and "config encrypt" not in saved


def test_encryption_notice_for_a_backend_under_claude_cfg(backend_from_init):
    pushed = one_line(invoke("push", "one"))
    assert ("This snapshot is not encrypted. Run `claude-cfg config encrypt` "
            "to encrypt future pushes.") in pushed


def test_encryption_notice_for_a_backend_in_the_plugin(plugin_name, backend_from_init):
    saved = one_line(invoke("save", "one"))
    assert ("This version is not encrypted. Run `claude-cfg config encrypt` in a terminal "
            "to encrypt future saves.") in saved
    assert "config-history config encrypt" not in saved


def test_autosave_off_text_under_each_name(monkeypatch, local_history):
    off = dict(local_history, autosave={"enabled": False})
    assert autosave_state_text(off) == (
        "Auto-save is off. Turn it on with `claude-cfg config autosave --enable`."
    )
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    assert autosave_state_text(off) == (
        "Auto-save is off. Ask Claude to turn it on "
        "(it runs `config-history config autosave --enable`)."
    )


@pytest.mark.parametrize("use_plugin, expected", [
    (False, "Not tracked yet: keybindings.json. Run `claude-cfg config track-defaults` "
            "to add them."),
    (True, "Not tracked yet: keybindings.json. Ask Claude to track them too "
           "(it runs `config-history config track-defaults`)."),
])
def test_untracked_defaults_hint_under_each_name(monkeypatch, backend_from_init, use_plugin,
                                                 expected):
    if use_plugin:
        monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    write_files(claude_dir(), {"keybindings.json": "{}"})
    assert expected in one_line(invoke("save", "one"))


def test_terminal_only_commands_under_each_name(monkeypatch):
    assert mismatch_message().endswith("run `claude-cfg config encrypt` to set it again.")
    assert unavailable_message().endswith(
        "`claude-cfg config encrypt`, or run the command in a terminal."
    )
    assert files_only_undo_text() == (
        "Run `claude-cfg undo` from a normal terminal, or `claude-cfg undo --files-only` "
        "to put the files back now and the MCP servers later."
    )
    assert no_snapshots_message() == "No snapshots found. Run `claude-cfg push` first."
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    assert mismatch_message().endswith(
        "run `claude-cfg config encrypt` in a terminal to set it again."
    )
    assert unavailable_message().endswith("save one with `claude-cfg config encrypt` in a terminal.")
    assert files_only_undo_text() == (
        "Run `claude-cfg undo` from a normal terminal, or ask Claude to put the files back now "
        "and the MCP servers later (it runs `config-history undo --files-only`)."
    )
    assert no_snapshots_message() == "No versions saved yet. Ask Claude to save a version first."


def test_skipped_autosave_without_passphrase_under_each_name(monkeypatch):
    skipped = AutoSaveResult(AutoSaveOutcome.NO_PASSPHRASE)
    assert autosave_summary(skipped).endswith("or run `claude-cfg save` to type it.")
    assert autosave_line(skipped).endswith("or run: claude-cfg save")
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    assert autosave_summary(skipped).endswith("or run `claude-cfg save` in a terminal to type it.")
    assert autosave_line(skipped).endswith("or run `claude-cfg save` in a terminal.")


def test_mcp_sync_off_text_in_the_plugin(plugin_name, capsys):
    print_mcp_sync_state(False)
    assert one_line(capsys.readouterr().out) == (
        "MCP server sync is off. Turn it on with `claude-cfg config mcp --enable` in a terminal."
    )
