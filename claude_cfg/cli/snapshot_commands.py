"""The push and list (also history) commands."""

from typing import Optional

import typer
from rich.markup import escape

from claude_cfg import core
from claude_cfg.cli.command_context import (
    REPEAT_PROMPT_TEXT,
    load_config_or_exit,
    passphrase_prompt_pausing,
    reported_errors,
)
from claude_cfg.cli.history_output import print_history
from claude_cfg.cli.output import console, print_push_result
from claude_cfg.command_wording import wording_for
from claude_cfg.paths import claude_dir
from claude_cfg.program_name import ask_claude_text, command_hint, uses_slash_commands
from claude_cfg.providers import get_provider
from claude_cfg.tracked_defaults import untracked_defaults_on_disk


def push_command(
    message: str = typer.Argument("", help="Snapshot message"),
) -> None:
    """Push current ~/.claude/ config as a new snapshot."""
    cfg = load_config_or_exit()
    provider = get_provider(cfg)
    with reported_errors(), console.status("Pushing snapshot...") as status:
        result = core.push(
            message,
            cfg,
            provider,
            passphrase_prompt=passphrase_prompt_pausing(status),
            repeat_prompt=passphrase_prompt_pausing(status, REPEAT_PROMPT_TEXT),
        )
    print_push_result(result, wording_for(cfg))
    _print_untracked_defaults_hint(cfg)


def _print_untracked_defaults_hint(cfg: dict) -> None:
    """One dim line when default entries exist on disk but are not tracked."""
    untracked = untracked_defaults_on_disk(cfg.get("tracked", []), claude_dir())
    if not untracked:
        return
    if uses_slash_commands():
        how = ask_claude_text("config track-defaults", "track them too")
    else:
        how = f"Run `{command_hint('config track-defaults')}` to add them."
    console.print(f"[dim]Not tracked yet: {escape(', '.join(untracked))}. {escape(how)}[/dim]")


def list_command(
    keys: bool = typer.Option(False, "--keys", help="Also show each snapshot's object key."),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        min=1,
        help="Show at most this many, newest first (default: 10 for the local history, "
        "all for a sync backend).",
    ),
) -> None:
    """List the saved versions, newest first."""
    cfg = load_config_or_exit()
    provider = get_provider(cfg)
    with reported_errors():
        snapshots = core.list_snapshots(provider)
    wording = wording_for(cfg)
    if not snapshots:
        console.print("No versions saved yet." if wording.local_words else "No snapshots found.")
        return
    print_history(snapshots, wording, limit=limit, show_keys=keys)
