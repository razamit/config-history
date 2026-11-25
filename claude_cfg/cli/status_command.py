"""The status command, including its ``--hook`` mode for Claude Code."""

from contextlib import nullcontext

import typer

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli.command_context import load_config_or_exit
from claude_cfg.cli.output import console
from claude_cfg.cli.status_output import print_status
from claude_cfg.command_wording import wording_for
from claude_cfg.providers import get_provider
from claude_cfg.session_start_notice import DEFAULT_TIME_LIMIT_SECONDS, SessionStartNoticeManager
from claude_cfg.sync_status import RemoteStatus

# Tests shorten this; the hook's own timeout in settings.json is 10 seconds.
HOOK_TIME_LIMIT_SECONDS = DEFAULT_TIME_LIMIT_SECONDS


def _remote_status_for(cfg: dict) -> RemoteStatus:
    return core.remote_status(lambda: get_provider(cfg))


def run_status_hook() -> None:
    """Print one ``systemMessage`` line when the backend has newer, else nothing."""
    manager = SessionStartNoticeManager(cfg_mod.load, _remote_status_for, HOOK_TIME_LIMIT_SECONDS)
    notice = manager.notice_json()
    if notice:
        typer.echo(notice)


def status_command(
    offline: bool = typer.Option(
        False, "--offline", help="Skip the backend and only check local changes."
    ),
    show_all: bool = typer.Option(False, "--all", help="List every changed file."),
    hook: bool = typer.Option(
        False,
        "--hook",
        help="SessionStart hook mode: print a JSON notice only when the backend has a newer "
        "snapshot. Never prompts, always exits 0.",
    ),
) -> None:
    """Show what changed here since the last push or pull, and whether the backend has newer."""
    if hook:
        try:
            run_status_hook()
        except BaseException:  # noqa: BLE001 - a hook must always exit 0
            pass
        return
    cfg = load_config_or_exit()
    provider_factory = None if offline else (lambda: get_provider(cfg))
    spinner = nullcontext() if offline else console.status("Checking the backend...")
    with spinner:
        sync_status = core.status(cfg, provider_factory=provider_factory)
    print_status(sync_status, show_all, wording_for(cfg))
