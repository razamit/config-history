"""Printing MCP server changes. Only server names are ever printed, never a
definition, an env value or a header."""

from typing import Optional

from rich.markup import escape

from claude_cfg.cli.file_list_output import print_file_group
from claude_cfg.cli.output import console
from claude_cfg.mcp_server_plan import McpServerPlan
from claude_cfg.mcp_server_sync import McpApplyResult

ONLY_LOCAL_NOTE = "a normal pull keeps these; `pull --exact` would remove them"


def print_mcp_plan(mcp_plan: Optional[McpServerPlan], show_all: bool, list_only_local: bool) -> None:
    if mcp_plan is None:
        return
    console.print("[bold]MCP servers (user scope)[/bold]")
    print_file_group("Add server", mcp_plan.to_add, show_all, style="green", marker="+")
    print_file_group("Replace server", mcp_plan.to_replace, show_all, style="yellow", marker="~")
    print_file_group("Remove server", mcp_plan.to_remove, show_all, style="red", marker="-")
    console.print(f"[dim]Unchanged: {len(mcp_plan.unchanged)} server(s)[/dim]")
    if list_only_local:
        print_file_group("Servers only on this machine", mcp_plan.only_local, show_all, note=ONLY_LOCAL_NOTE)


def print_mcp_pull_result(mcp_summary: Optional[dict]) -> None:
    """The ``mcp`` part of a pull result from :func:`claude_cfg.core.describe_pull`."""
    if not mcp_summary:
        return
    failed = mcp_summary.get("failed", {})
    counts = (len(mcp_summary["added"]), len(mcp_summary["replaced"]), len(mcp_summary["removed"]))
    skipped_reason = mcp_summary.get("skipped_reason")
    if skipped_reason:
        print_mcp_skipped(skipped_reason, "No MCP server was changed. The files were restored either way.")
    elif any(counts):
        console.print(
            f"  MCP servers: {counts[0]} added, {counts[1]} replaced, {counts[2]} removed, "
            f"{mcp_summary.get('unchanged', 0)} unchanged"
        )
    print_mcp_failures(failed, "The files were restored either way.")


def print_mcp_skipped(reason: str, note: str) -> None:
    console.print(f"  [yellow]MCP servers skipped: {escape(reason)}. {escape(note)}[/yellow]")


def print_mcp_failures(failed: dict[str, str], note: str) -> None:
    if not failed:
        return
    console.print(
        f"  [yellow]{len(failed)} MCP server change(s) were not applied. {escape(note)}[/yellow]"
    )
    for name, reason in sorted(failed.items()):
        console.print(f"    [yellow]! {escape(name)}: {escape(reason)}[/yellow]")


def print_mcp_undo_result(result: Optional[McpApplyResult]) -> None:
    if result is None:
        return
    if result.skipped_reason:
        print_mcp_skipped(result.skipped_reason, "No MCP server was put back. The files were put back either way.")
    if result.applied:
        console.print(f"  MCP servers put back: {escape(', '.join(result.applied))}")
    print_mcp_failures(result.failed, "The files were put back either way.")
