"""Printing ``claude-cfg status``."""

from typing import Optional

from rich.markup import escape

from claude_cfg.cli.file_list_output import print_file_group
from claude_cfg.cli.output import console, format_timestamp, shown
from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.program_name import command_hint
from claude_cfg.sync_status import SuggestedAction, SyncStatus


def next_step_text(action: SuggestedAction, wording: Optional[CommandWording] = None) -> str:
    """The closing line of ``status``, naming the command the user types."""
    wording = wording or wording_for(None)
    save, restore, run = wording.save_verb, wording.restore_verb, wording.run_word
    if wording.local_words:
        # With a local history this is the state after going back to an
        # earlier version, so say how to return rather than "get".
        newer_step = f"Next: a newer version exists. {run} `{wording.command(restore)}` to return to it."
    else:
        newer_step = f"Next: run `{wording.command(restore)}` to get the newer snapshot."
    if wording.slash_commands:
        # The history skill takes plain words; "/config-history:history save" reads oddly.
        save_step = "Next: to keep this machine's changes, ask Claude to save a version now."
    else:
        save_step = f"Next: {run.lower()} `{wording.command(save)}` to save this machine's changes."
    texts = {
        SuggestedAction.PUSH: save_step,
        SuggestedAction.PULL: newer_step,
        SuggestedAction.REVIEW: (
            f"Next: both sides changed. {run} `{command_hint('diff')}` to compare, then {save} or "
            f"{restore}. A {restore} overwrites the local edits (`{command_hint('undo')}` reverts it)."
        ),
        SuggestedAction.NONE: "Nothing to do.",
    }
    return texts[action]


def print_status(
    status: SyncStatus, show_all: bool, wording: Optional[CommandWording] = None
) -> None:
    """Last save, local changes, the remote (unless the history is on this
    machine), then the next step."""
    wording = wording or wording_for(None)
    if wording.local_words:
        _print_last_saved(status)
    else:
        _print_last_synced(status)
    _print_local_changes(status, show_all)
    if not wording.history_on_this_machine:
        _print_remote(status)
    console.print(f"[bold]{escape(next_step_text(status.suggested_action, wording))}[/bold]")


def _print_last_saved(status: SyncStatus) -> None:
    """``Last saved: version N (...)``, or ``Last restored`` after a restore."""
    state = status.last_synced
    if state is None:
        console.print("Last saved: never on this machine.")
        return
    if state.action == "pull":
        console.print(
            f"Last restored: version [cyan]{state.snapshot_id}[/cyan] from "
            f"{format_timestamp(state.snapshot_timestamp)}, restored {format_timestamp(state.synced_at)}"
        )
        return
    console.print(
        f"Last saved: version [cyan]{state.snapshot_id}[/cyan], {format_timestamp(state.synced_at)}"
    )


def _print_last_synced(status: SyncStatus) -> None:
    state = status.last_synced
    if state is None:
        console.print("Last synced: never on this machine.")
        return
    console.print(
        f"Last synced: snapshot [cyan]#{state.snapshot_id}[/cyan] from {shown(state.machine)}, "
        f"taken {format_timestamp(state.snapshot_timestamp)}; "
        f"{escape(state.action)}ed {format_timestamp(state.synced_at)}"
    )


def _print_local_changes(status: SyncStatus, show_all: bool) -> None:
    if status.local_error:
        console.print(f"[yellow]Local changes: could not check ({escape(status.local_error)})[/yellow]")
        return
    changes = status.local_changes
    if changes is None:
        return
    if not changes.has_changes:
        console.print("Local changes: none.")
        return
    console.print(
        f"Local changes: {len(changes.added)} added, {len(changes.modified)} modified, "
        f"{len(changes.removed)} removed"
    )
    groups = (
        ("Added", changes.added, "green", "+"),
        ("Modified", changes.modified, "yellow", "~"),
        ("Removed", changes.removed, "red", "-"),
    )
    for title, paths, style, marker in groups:
        if paths:
            print_file_group(title, paths, show_all, style=style, marker=marker)


def _print_remote(status: SyncStatus) -> None:
    remote = status.remote
    if not remote.checked:
        console.print("[dim]Remote: not checked (--offline).[/dim]")
    elif remote.error:
        console.print(f"[yellow]Remote: could not check ({escape(remote.error)})[/yellow]")
    elif remote.latest is None:
        console.print("Remote: no snapshots yet.")
    else:
        latest = remote.latest
        verdict = "newer than this machine" if remote.is_newer else "nothing newer"
        console.print(
            f"Remote latest: snapshot [cyan]#{latest.snapshot_id}[/cyan] from {shown(latest.machine)}, "
            f"taken {format_timestamp(latest.timestamp)}; {verdict}"
        )
