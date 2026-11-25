"""Shared console and the formatting of command results."""

from typing import Optional

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.display_text import printable_text
from claude_cfg.program_name import command_hint

console = Console()

_SUMMARY_LIMIT = 5


def shown(text: object) -> str:
    """Backend-supplied text, ready to put in a console markup string: hidden
    and control characters removed, rich markup escaped."""
    return escape(printable_text(text))


def format_timestamp(timestamp: str) -> str:
    """``2026-05-06T14:32:00Z`` becomes ``2026-05-06 14:32:00``, ready for markup."""
    return shown(str(timestamp).replace("T", " ").replace("Z", ""))


def print_error(message: str) -> None:
    console.print(f"[red]{escape(message)}[/red]")


def print_push_result(result: dict, wording: Optional[CommandWording] = None) -> None:
    wording = wording or wording_for(None)
    size_kb = result["size_bytes"] / 1024
    console.print(
        f"[green]{wording.version_label(result['id'])} {wording.saved_word} "
        f"({format_timestamp(result['timestamp'])}), "
        f"{result['file_count']} files, {size_kb:.1f} KB[/green]"
    )
    if not result.get("encrypted"):
        print_unencrypted_notice()
    if result.get("index_updated") is False:
        console.print(
            "[dim]The snapshot is stored, but the index cache could not be "
            "updated. Listing still works and the cache is fixed on the next push.[/dim]"
        )


def print_unencrypted_notice() -> None:
    console.print(
        f"[dim]This snapshot is not encrypted. Run `{escape(command_hint('config encrypt'))}` "
        "to encrypt future pushes.[/dim]"
    )


def print_restore_result(result: dict, wording: Optional[CommandWording] = None) -> None:
    """A finished restore. The sign-in reminder shows only for a snapshot taken
    on another machine, since credentials never travel with it."""
    wording = wording or wording_for(None)
    console.print(
        f"[green]{wording.version_label(result['id'])} restored "
        f"({format_timestamp(result['timestamp'])}): {result.get('created', 0)} created, "
        f"{result.get('overwritten', 0)} overwritten, {result.get('deleted', 0)} deleted, "
        f"{result.get('unchanged', 0)} unchanged[/green]"
    )
    if result.get("message"):
        console.print(f"  Message: {shown(result['message'])}")
    _print_backup_lines(result, wording)
    _print_platform_adaptation(result)
    if result.get("from_other_machine", True):
        console.print(
            "  [yellow]Credentials are never synced. Run [bold]claude[/bold] "
            "to sign in again.[/yellow]"
        )


def _print_backup_lines(result: dict, wording: CommandWording) -> None:
    if result.get("kept_local"):
        console.print(
            f"  [dim]Kept {result['kept_local']} file(s) that exist only on this machine "
            f"(`{escape(wording.exact_restore_hint())}` removes them).[/dim]"
        )
    if result.get("refused_deletes"):
        console.print(
            f"  [yellow]Skipped deleting {len(result['refused_deletes'])} file(s) that are "
            "excluded, outside the tracked folders, or behind a symlink.[/yellow]"
        )
    if result.get("backup_dir"):
        console.print(
            f"  [dim]Replaced files backed up to {escape(result['backup_dir'])}. "
            f"Run `{escape(command_hint('undo'))}` to revert this {wording.restore_verb}.[/dim]"
        )
    else:
        console.print("  [dim]Nothing changed, so no backup was made.[/dim]")


def _print_platform_adaptation(result: dict) -> None:
    source, target = result.get("source_platform"), result.get("target_platform")
    launcher = result.get("python_launcher")
    if source and target and source != target:
        detail = "paths re-tokenized"
        if launcher:
            detail += f", python commands → {launcher}"
        console.print(f"  [dim]Adapted {source} → {target} ({detail}).[/dim]")
    if result.get("is_wsl"):
        console.print(
            "  [yellow]WSL detected: this is the Linux home, distinct from any "
            "Windows-native ~/.claude.[/yellow]"
        )


def print_snapshot_table(snapshots: list[dict], show_keys: bool = False) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", width=4)
    table.add_column("Timestamp", width=21)
    table.add_column("Message", width=30)
    table.add_column("Machine")
    table.add_column("Encrypted")
    if show_keys:
        table.add_column("Key")
    for snapshot in snapshots:
        row = [
            str(snapshot["id"]),
            format_timestamp(snapshot["timestamp"]),
            shown(snapshot.get("message", "")),
            shown(snapshot.get("machine", "")),
            "yes" if snapshot.get("encrypted") else "no",
        ]
        if show_keys:
            row.append(shown(snapshot.get("key", "")))
        table.add_row(*row)
    console.print(table)


def print_snapshot_summary(snapshots: list[dict]) -> None:
    """A short newest-first list, used by the init wizard."""
    console.print(f"\n[bold]This backend already has {len(snapshots)} snapshot(s):[/bold]")
    for snapshot in snapshots[:_SUMMARY_LIMIT]:
        console.print(
            f"  [cyan]#{snapshot['id']}[/cyan]  {format_timestamp(snapshot['timestamp'])}"
            f"  {shown(snapshot.get('message', ''))}"
            f"  [dim]{shown(snapshot.get('machine', ''))}[/dim]"
        )
    if len(snapshots) > _SUMMARY_LIMIT:
        console.print(f"  [dim]…and {len(snapshots) - _SUMMARY_LIMIT} more[/dim]")
