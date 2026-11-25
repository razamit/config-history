"""The pull, diff and undo commands."""

import sys
from typing import Optional

import typer

from claude_cfg import core
from claude_cfg.cli.command_context import (
    load_config_or_exit,
    passphrase_prompt_pausing,
    reported_errors,
)
from claude_cfg.cli.file_list_output import print_file_group
from claude_cfg.cli.output import console, print_error
from claude_cfg.command_wording import wording_for, wording_for_saved_config
from claude_cfg.cli.restore_output import (
    print_plan,
    print_pull_preview,
    print_pull_result,
    print_undo_conflicts,
    print_undo_result,
)
from claude_cfg.errors import ConfirmationRequiredError, UndoConflictError
from claude_cfg.providers import get_provider
from claude_cfg.pull_manager import PreparedPull
from claude_cfg.restore_writer import RestoreWriter

POINT_OPTION = typer.Option(None, "--point", help="Snapshot ID (default: the latest).")
KEY_OPTION = typer.Option(
    None, "--key", help="Exact snapshot object key, as shown by `list --keys`."
)
ALL_OPTION = typer.Option(False, "--all", help="List every file instead of the first 20 per group.")
ALLOW_PLAIN_OPTION = typer.Option(
    False,
    "--allow-plain",
    help="Accept a snapshot that is not encrypted although encryption is on here "
    "(for snapshots pushed before encryption was turned on).",
)


def stdin_is_interactive() -> bool:
    """Whether a person can answer a prompt. Tests replace this."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _reject_point_and_key(point: Optional[int], key: Optional[str]) -> None:
    if point is not None and key is not None:
        print_error("Pass either --point or --key, not both.")
        raise typer.Exit(1)


def _prepare(
    cfg: dict, point: Optional[int], key: Optional[str], exact: bool, allow_plain: bool
) -> PreparedPull:
    provider = get_provider(cfg)
    with console.status("Fetching snapshot...") as status:
        return core.prepare_pull(
            point, cfg, provider, key=key, exact=exact,
            passphrase_prompt=passphrase_prompt_pausing(status), allow_plain=allow_plain,
        )


def _servers_to_remove(prepared: PreparedPull) -> list[str]:
    return prepared.mcp_plan.to_remove if prepared.mcp_plan is not None else []


def _confirm_deletions(prepared: PreparedPull, assume_yes: bool, show_all: bool) -> None:
    """Show what --exact deletes and ask, or refuse when nobody can answer."""
    to_delete, servers = prepared.plan.to_delete, _servers_to_remove(prepared)
    print_file_group("Delete", to_delete, show_all, style="red", marker="-")
    if servers:
        print_file_group("Remove MCP server", servers, show_all, style="red", marker="-")
    what = f"{len(to_delete)} file(s)" + (f" and {len(servers)} MCP server(s)" if servers else "")
    if assume_yes:
        return
    if not stdin_is_interactive():
        raise ConfirmationRequiredError(
            f"pull --exact would delete {what} and there is no "
            "terminal to confirm on. Pass --yes to delete them, or run without --exact."
        )
    if not typer.confirm(f"Delete these {what} from the Claude config?", default=False):
        console.print("Pull cancelled. Nothing was changed.")
        raise typer.Exit(1)


def pull_command(
    point: Optional[int] = POINT_OPTION,
    key: Optional[str] = KEY_OPTION,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change and write nothing."),
    exact: bool = typer.Option(
        False, "--exact", help="Also delete tracked local files the snapshot does not have."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before --exact deletes files."),
    show_all: bool = ALL_OPTION,
    allow_plain: bool = ALLOW_PLAIN_OPTION,
) -> None:
    """Pull a snapshot and restore it to ~/.claude/."""
    _reject_point_and_key(point, key)
    cfg = load_config_or_exit()
    with reported_errors():
        prepared = _prepare(cfg, point, key, exact, allow_plain)
        if dry_run:
            print_pull_preview(prepared, show_all, wording_for(cfg))
            return
        RestoreWriter.check_destinations(prepared.plan)  # refuse swaps before asking anything
        if prepared.plan.to_delete or _servers_to_remove(prepared):
            _confirm_deletions(prepared, yes, show_all)
        result = core.apply_pull(prepared, cfg)
    print_pull_result(result, wording_for(cfg))


def diff_command(
    point: Optional[int] = POINT_OPTION,
    key: Optional[str] = KEY_OPTION,
    show_all: bool = ALL_OPTION,
    allow_plain: bool = ALLOW_PLAIN_OPTION,
) -> None:
    """Compare ~/.claude/ with a snapshot (the latest by default). Writes nothing."""
    _reject_point_and_key(point, key)
    cfg = load_config_or_exit()
    with reported_errors():
        prepared = _prepare(cfg, point, key, exact=False, allow_plain=allow_plain)
    print_plan(prepared, show_all, list_only_local=True, wording=wording_for(cfg))


def undo_command(
    force: bool = typer.Option(
        False, "--force", help="Revert even files that changed after the pull."
    ),
    files_only: bool = typer.Option(
        False,
        "--files-only",
        help="Put the files back now and leave MCP server changes for a later undo "
        "from a normal terminal.",
    ),
    show_all: bool = ALL_OPTION,
) -> None:
    """Revert the most recent pull that has not been undone."""
    with reported_errors():
        try:
            result = core.undo(force=force, files_only=files_only)
        except UndoConflictError as conflict:
            print_undo_conflicts(conflict.changed_files, show_all)
            raise
    print_undo_result(result, wording_for_saved_config())
