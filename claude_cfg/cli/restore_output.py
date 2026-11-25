"""Printing restore plans and undo results."""

from typing import Optional

from rich.markup import escape

from claude_cfg.change_summary import change_text
from claude_cfg.cli.file_list_output import print_file_group
from claude_cfg.cli.mcp_output import print_mcp_plan, print_mcp_pull_result, print_mcp_undo_result
from claude_cfg.cli.output import console, format_timestamp, print_restore_result, shown
from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.program_name import terminal_command_hint
from claude_cfg.pull_manager import PreparedPull
from claude_cfg.undo_manager import UndoResult


def only_local_note(wording: CommandWording) -> str:
    return f"a normal {wording.restore_verb} keeps these; {wording.extras_removal_text()}"


def print_snapshot_heading(prepared: PreparedPull, wording: Optional[CommandWording] = None) -> None:
    """``Version 3, saved 2 hours ago (today 18:11): message``, then the
    ``--only`` paths when the restore is partial."""
    wording = wording or wording_for(None)
    entry = prepared.entry
    message = prepared.contents.manifest.get("message", entry.message)
    if wording.local_words:
        message = change_text(message, entry.automatic)
    message = shown(message)
    console.print(
        f"{wording.version_label(entry.snapshot_id, markup=True)}, {wording.saved_word} "
        f"{format_timestamp(entry.timestamp)}" + (f": {message}" if message else "")
    )
    if prepared.plan.only_paths:
        console.print(f"Only: {shown(', '.join(prepared.plan.only_paths))}")


def print_plan(
    prepared: PreparedPull,
    show_all: bool,
    list_only_local: bool,
    wording: Optional[CommandWording] = None,
) -> None:
    """The create, overwrite and delete groups, then what stays the same.

    ``list_only_local`` lists local extras by name, as ``diff`` always does.
    Otherwise a normal pull only mentions how many it keeps.
    """
    wording = wording or wording_for(None)
    plan = prepared.plan
    print_snapshot_heading(prepared, wording)
    print_file_group("Create", plan.to_create, show_all, style="green", marker="+")
    print_file_group("Overwrite", plan.to_overwrite, show_all, style="yellow", marker="~")
    print_file_group("Delete", plan.to_delete, show_all, style="red", marker="-")
    console.print(f"[dim]Unchanged: {len(plan.unchanged)} file(s)[/dim]")
    if list_only_local:
        print_file_group(
            "Only on this machine", plan.only_local, show_all, note=only_local_note(wording)
        )
    elif plan.only_local and not plan.exact:
        console.print(
            f"[dim]Kept: {len(plan.only_local)} file(s) only on this machine "
            f"({escape(wording.extras_removal_text())})[/dim]"
        )
    print_left_untouched(plan.left_untouched)
    if plan.conflicts:
        print_file_group("File and folder swapped (pull stops)", plan.conflicts, show_all, style="red", marker="!")
    print_mcp_plan(prepared.mcp_plan, show_all, list_only_local)


def print_left_untouched(left_untouched: dict[str, str]) -> None:
    for relative_path, reason in sorted(left_untouched.items()):
        console.print(f"  [yellow]{escape(relative_path)}: {escape(reason)}[/yellow]")


def print_pull_result(result: dict, wording: Optional[CommandWording] = None) -> None:
    """A finished pull: the file summary, then any MCP server changes."""
    print_restore_result(result, wording)
    print_left_untouched(result.get("left_untouched", {}))
    print_mcp_pull_result(result.get("mcp"))
    if result.get("session_hook_removed"):
        console.print(
            "  [yellow]This snapshot's settings.json removed the claude-cfg session hook. "
            f"Run `{escape(terminal_command_hint('integrate install'))}`, then "
            f"`{escape(terminal_command_hint('push'))}`, to keep it.[/yellow]"
        )


def print_pull_preview(
    prepared: PreparedPull, show_all: bool, wording: Optional[CommandWording] = None
) -> None:
    print_plan(prepared, show_all, list_only_local=False, wording=wording)
    console.print("[bold]Dry run: nothing was written.[/bold]")


def print_undo_result(result: UndoResult, wording: Optional[CommandWording] = None) -> None:
    wording = wording or wording_for(None)
    undone = f"the {wording.restore_verb} of {wording.version_noun(result.snapshot_id)}"
    if result.restored_at:
        undone += f" from {format_timestamp(result.restored_at)}"
    if result.files_already_undone:
        console.print(
            f"[green]Finished undoing {undone}: "
            "its files were put back earlier, now its MCP servers.[/green]"
        )
    else:
        console.print(
            f"[green]Undid {undone}: "
            f"{len(result.restored)} file(s) put back, {len(result.removed)} removed.[/green]"
        )
    if result.mcp_left_pending:
        console.print(
            "  [yellow]MCP server changes were not put back (--files-only). Run "
            f"`{escape(terminal_command_hint('undo'))}` from a normal terminal to put them back.[/yellow]"
        )
    if result.overridden_changes:
        console.print(
            f"  [yellow]Replaced {len(result.overridden_changes)} file(s) that had "
            "changed after the pull (--force).[/yellow]"
        )
    print_mcp_undo_result(result.mcp_result)
    if not result.state_restored and not result.files_already_undone and not result.partial:
        console.print(
            "  [dim]The sync state was left as it is, because a later push or pull "
            "already moved it past this snapshot.[/dim]"
        )
    console.print(f"  [dim]Backup used: {escape(str(result.backup_dir))}[/dim]")


def print_undo_conflicts(changed_files: list[str], show_all: bool) -> None:
    print_file_group("Changed since the pull", changed_files, show_all, style="yellow", marker="!")
