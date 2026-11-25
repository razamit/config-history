"""The lines ``session-hook start`` shows the user, one per fact.

Every line starts with the program name and names commands the way the user
types them: a slash command inside the plugin, a shell command otherwise
(see :mod:`claude_cfg.program_name` and :mod:`claude_cfg.command_wording`).
"""

from typing import Optional

from claude_cfg.autosave_manager import AutoSaveOutcome, AutoSaveResult, ChangeReport
from claude_cfg.autosave_message import count_text, file_list_text
from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.program_name import (
    command_hint,
    program_name,
    shell_command_hint,
    terminal_command_text,
    uses_slash_commands,
)


def autosave_line(
    result: Optional[AutoSaveResult], wording: Optional[CommandWording] = None
) -> Optional[str]:
    """What an auto-save did, or None when there is nothing to tell."""
    if result is None:
        return None
    if result.outcome is AutoSaveOutcome.SAVED:
        return _saved_line(result, wording or wording_for(None))
    if result.outcome is AutoSaveOutcome.NO_PASSPHRASE:
        return _no_passphrase_line()
    if result.outcome is AutoSaveOutcome.FAILED:
        return f"{program_name()}: auto-save failed ({result.reason})."
    return None


def _no_passphrase_line() -> str:
    """Auto-save needs a passphrase nobody can type here. Inside the plugin
    a save that prompts runs only from a terminal, as ``claude-cfg save``."""
    if uses_slash_commands():
        how = f"or run {terminal_command_text('save')}."
    else:
        how = f"or run: {shell_command_hint('save')}"
    return (
        f"{program_name()}: your settings changed, but auto-save skipped them: encryption "
        f"is on and no passphrase is available without a prompt. Set {PASSPHRASE_ENV_VAR} {how}"
    )


def _saved_line(result: AutoSaveResult, wording: CommandWording) -> str:
    name = program_name()
    if result.first_version:
        return f"{name}: saved version {result.snapshot_id}, the first version of your settings."
    changed = result.changed_paths
    line = (
        f"{name}: saved version {result.snapshot_id} "
        f"({count_text(len(changed))} changed: {file_list_text(changed)})."
    )
    if result.previous_id is not None:
        line += f" {wording.go_back_text(result.previous_id)}"
    return line


def unsaved_changes_line(report: Optional[ChangeReport]) -> Optional[str]:
    """For auto-save off: a reminder to save when something changed."""
    if report is None or report.error:
        return None
    if report.first_version:
        return (
            f"{program_name()}: no version of your settings is saved yet. "
            f"Save one with: {command_hint('save')}"
        )
    if not report.changed_paths:
        return None
    changed = report.changed_paths
    return (
        f"{program_name()}: {count_text(len(changed))} changed since the last saved version "
        f"({file_list_text(changed)}). Save them with: {command_hint('save')}"
    )


def autosave_held_line(wording: Optional[CommandWording] = None) -> str:
    """Auto-save waits while the backend has a newer snapshot than this machine."""
    wording = wording or wording_for(None)
    return (
        f"{program_name()}: auto-save is waiting so it does not save over the newer snapshot. "
        f"Run `{wording.command(wording.restore_verb)}` or `{command_hint('save')}` first."
    )
