"""``session-hook start`` and ``session-hook end``, for Claude Code hooks.

Both always exit 0 and never prompt. ``start`` prints nothing or one JSON
line; ``end`` prints nothing. See :mod:`claude_cfg.session_hook_manager`.
"""

import typer

from claude_cfg import core
from claude_cfg.autosave_manager import AutoSaveResult
from claude_cfg.autosave_setup import build_autosave_manager, detect_local_changes
from claude_cfg.default_history import load_or_create_config
from claude_cfg.providers import get_provider
from claude_cfg.session_hook_manager import (
    SessionHookActions,
    SessionHookManager,
    SessionHookTimeLimits,
)
from claude_cfg.sync_status import RemoteStatus

session_hook_app = typer.Typer(
    help="Commands that Claude Code hooks run. They never prompt and always exit 0.",
    pretty_exceptions_show_locals=False,
)

# Tests shorten these.
TIME_LIMITS = SessionHookTimeLimits()


def _check_remote(cfg: dict) -> RemoteStatus:
    return core.remote_status(lambda: get_provider(cfg))


def _run_autosave(cfg: dict) -> AutoSaveResult:
    return build_autosave_manager(cfg, provider_factory=lambda c: get_provider(c)).run()


def build_session_hook_manager() -> SessionHookManager:
    actions = SessionHookActions(
        load_config=load_or_create_config,
        run_autosave=_run_autosave,
        detect_changes=detect_local_changes,
        check_remote=_check_remote,
    )
    return SessionHookManager(actions, TIME_LIMITS)


@session_hook_app.command("start")
def session_hook_start() -> None:
    """For SessionStart: auto-save, then print one JSON notice or nothing."""
    try:
        notice = build_session_hook_manager().start_notice_json()
        if notice:
            typer.echo(notice)
    except BaseException:  # noqa: BLE001 - a hook must always exit 0
        pass


@session_hook_app.command("end")
def session_hook_end() -> None:
    """For SessionEnd: auto-save when it is on. Prints nothing."""
    try:
        build_session_hook_manager().run_end()
    except BaseException:  # noqa: BLE001 - a hook must always exit 0
        pass
