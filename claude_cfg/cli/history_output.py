"""Printing ``list`` (also ``history``).

In local-history wording the list is three plain columns: Version, When and
What changed. A sync backend under the ``claude-cfg`` name keeps its own
table (:func:`claude_cfg.cli.output.print_snapshot_table`), with local times.
"""

from typing import Optional

from rich.table import Table

from claude_cfg.change_summary import change_text
from claude_cfg.cli.output import console, format_timestamp, print_snapshot_table, shown
from claude_cfg.command_wording import CommandWording

LOCAL_DEFAULT_LIMIT = 10


def default_limit(wording: CommandWording) -> Optional[int]:
    """How many rows to show when ``--limit`` is not given: 10 in local
    wording, every row for a sync backend."""
    return LOCAL_DEFAULT_LIMIT if wording.local_words else None


def print_plain_history(snapshots: list, show_keys: bool = False) -> None:
    """Version, When and What changed, newest first."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Version", style="cyan", justify="right")
    table.add_column("When")
    table.add_column("What changed")
    if show_keys:
        table.add_column("Key")
    for snapshot in snapshots:
        row = [
            str(snapshot["id"]),
            format_timestamp(snapshot["timestamp"]),
            shown(change_text(snapshot.get("message", ""), bool(snapshot.get("automatic")))),
        ]
        if show_keys:
            row.append(shown(snapshot.get("key", "")))
        table.add_row(*row)
    console.print(table)


def hidden_rows_text(hidden: int, total: int, wording: CommandWording) -> str:
    """The line under a cut list, saying how many older rows exist."""
    noun = "version" if wording.local_words else "snapshot"
    nouns = noun if hidden == 1 else noun + "s"
    verb = "is" if hidden == 1 else "are"
    return f"{hidden} older {nouns} {verb} not shown. Add --limit {total} to see every one."


def print_history(
    snapshots: list,
    wording: CommandWording,
    limit: Optional[int] = None,
    show_keys: bool = False,
) -> None:
    """The list for this wording, cut to ``limit`` rows (its default when None)."""
    limit = limit if limit is not None else default_limit(wording)
    shown_rows = snapshots if limit is None else snapshots[:limit]
    if wording.local_words:
        print_plain_history(shown_rows, show_keys)
    else:
        print_snapshot_table(shown_rows, show_keys)
    hidden = len(snapshots) - len(shown_rows)
    if hidden:
        console.print(f"[dim]{hidden_rows_text(hidden, len(snapshots), wording)}[/dim]")
