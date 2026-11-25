"""The lines ``session-hook start`` shows the user, one per fact.

Every line starts with the program name and names commands the way the user
types them (see :mod:`claude_cfg.program_name`).
"""

from typing import Optional

from claude_cfg.autosave_manager import AutoSaveOutcome, AutoSaveResult, ChangeReport
from claude_cfg.autosave_message import count_text, file_list_text
from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.program_name import command_hint, program_name


def autosave_line(result: Optional[AutoSaveResult]) -> Optional[str]:
    """What an auto-save did, or None when there is nothing to tell."""
    if result is None:
        return None
    if result.outcome is AutoSaveOutcome.SAVED:
        return _saved_line(result)
    if result.outcome is AutoSaveOutcome.NO_PASSPHRASE:
        return (
            f"{program_name()}: your settings changed, but auto-save skipped them: encryption "
            f"is on and no passphrase is available without a prompt. Set {PASSPHRASE_ENV_VAR} "
            f"or run: {command_hint('save')}"
        )
    if result.outcome is AutoSaveOutcome.FAILED:
        return f"{program_name()}: auto-save failed ({result.reason})."
    return None


def _saved_line(result: AutoSaveResult) -> str:
    name = program_name()
    if result.first_version:
        return f"{name}: saved version {result.snapshot_id}, the first version of your settings."
    changed = result.changed_paths
    line = (
        f"{name}: saved version {result.snapshot_id} "
        f"({count_text(len(changed))} changed: {file_list_text(changed)})."
    )
    if result.previous_id is not None:
        line += f" Go back with: {command_hint(f'restore --point {result.previous_id}')}"
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
