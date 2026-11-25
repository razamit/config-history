"""Printing a titled group of file paths, capped unless --all is given."""

from rich.markup import escape

from claude_cfg.cli.output import console

DEFAULT_LIST_LIMIT = 20


def print_file_group(
    title: str,
    paths: list[str],
    show_all: bool,
    style: str = "",
    marker: str = " ",
    note: str = "",
) -> None:
    """``Title (N):`` then one path per line, at most 20 unless ``show_all``."""
    suffix = f": [dim]{escape(note)}[/dim]" if note else ""
    console.print(f"[bold]{escape(title)} ({len(paths)})[/bold]{suffix}")
    shown = paths if show_all else paths[:DEFAULT_LIST_LIMIT]
    for path in shown:
        line = f"  {marker} {escape(path)}"
        console.print(f"[{style}]{line}[/{style}]" if style else line)
    hidden = len(paths) - len(shown)
    if hidden:
        console.print(f"  [dim]and {hidden} more (use --all to list them)[/dim]")
