"""``session-hook start`` and ``session-hook end``, run by Claude Code hooks.

Contract: ``start`` prints nothing, or exactly one JSON object
``{"systemMessage": ...}`` on one line, with one line of text per fact.
``end`` prints nothing. Neither ever raises or prompts, and each step runs
under a time limit, because Claude Code waits for these hooks.

For a backend the user set up with ``init``, the remote check runs first:
when the backend has a snapshot newer than this machine's last sync,
auto-save waits, so it never buries that snapshot under a new one.
"""

import json
from dataclasses import dataclass
from typing import Callable, List, Optional

from claude_cfg.autosave_manager import AutoSaveResult, ChangeReport
from claude_cfg.command_wording import wording_for
from claude_cfg.config import is_automatic_default, is_autosave_enabled
from claude_cfg.display_text import printable_text
from claude_cfg.session_hook_lines import autosave_held_line, autosave_line, unsaved_changes_line
from claude_cfg.session_start_notice import newer_snapshot_message, run_with_time_limit
from claude_cfg.sync_status import RemoteStatus

# Time budgets, which must nest. Claude Code gives the SessionStart hook 15 s
# (hooks/hooks.json in the plugin, and the hook ``integrate install`` writes).
# The plugin bootstrap gives ``session-hook start`` 12 s of that
# (START_HOOK_TIMEOUT_SECONDS in scripts/config_history_hook.py). Inside it,
# the remote check (3 s) and then the auto-save or change check (6 s) run one
# after the other: 9 s, which leaves 3 s for interpreter start and imports.
# SessionEnd runs detached from the hook, so its auto-save gets 20 s.
# tests/test_session_hook_budgets.py checks that these numbers nest.
REMOTE_TIME_LIMIT_SECONDS = 3.0
START_AUTOSAVE_TIME_LIMIT_SECONDS = 6.0
END_AUTOSAVE_TIME_LIMIT_SECONDS = 20.0
STARTUP_ALLOWANCE_SECONDS = 3.0


@dataclass(frozen=True)
class SessionHookActions:
    """What the hooks delegate. Each callable may raise or hang."""

    load_config: Callable[[], dict]
    run_autosave: Callable[[dict], AutoSaveResult]
    detect_changes: Callable[[dict], ChangeReport]
    check_remote: Callable[[dict], RemoteStatus]


@dataclass(frozen=True)
class SessionHookTimeLimits:
    remote_seconds: float = REMOTE_TIME_LIMIT_SECONDS
    start_autosave_seconds: float = START_AUTOSAVE_TIME_LIMIT_SECONDS
    end_autosave_seconds: float = END_AUTOSAVE_TIME_LIMIT_SECONDS


class SessionHookManager:
    def __init__(
        self, actions: SessionHookActions, limits: Optional[SessionHookTimeLimits] = None
    ) -> None:
        self._actions = actions
        self._limits = limits or SessionHookTimeLimits()

    def start_notice_json(self) -> Optional[str]:
        """The one JSON line for ``start``, or None to print nothing."""
        try:
            lines = [printable_text(line) for line in self._start_lines() if line]
            return json.dumps({"systemMessage": "\n".join(lines)}) if lines else None
        except BaseException:  # noqa: BLE001 - the hook must stay silent
            return None

    def run_end(self) -> None:
        """Auto-save when it is on. Never prints, never raises."""
        try:
            cfg = self._actions.load_config()
            if is_autosave_enabled(cfg) and not self._remote_is_newer(self._remote_status(cfg)):
                self._timed(lambda: self._actions.run_autosave(cfg), self._limits.end_autosave_seconds)
        except BaseException:  # noqa: BLE001 - the hook must stay silent
            pass

    def _start_lines(self) -> List[Optional[str]]:
        cfg = self._actions.load_config()
        remote = self._remote_status(cfg)
        if is_autosave_enabled(cfg):
            first_line = self._autosave_or_held_line(cfg, self._remote_is_newer(remote))
        else:
            first_line = unsaved_changes_line(
                self._timed(lambda: self._actions.detect_changes(cfg), self._limits.start_autosave_seconds)
            )
        remote_line = newer_snapshot_message(remote, wording_for(cfg)) if remote is not None else None
        return [first_line, remote_line]

    def _autosave_or_held_line(self, cfg: dict, remote_newer: bool) -> Optional[str]:
        limit = self._limits.start_autosave_seconds
        if not remote_newer:
            return autosave_line(self._timed(lambda: self._actions.run_autosave(cfg), limit))
        report = self._timed(lambda: self._actions.detect_changes(cfg), limit)
        if report is None or not report.needs_save:
            return None
        return autosave_held_line(wording_for(cfg))

    def _remote_status(self, cfg: dict) -> Optional[RemoteStatus]:
        """The backend check, only for a backend the user set up, else None."""
        if is_automatic_default(cfg):
            return None
        return self._timed(lambda: self._actions.check_remote(cfg), self._limits.remote_seconds)

    @staticmethod
    def _remote_is_newer(remote: Optional[RemoteStatus]) -> bool:
        return remote is not None and remote.is_newer and not remote.error

    @staticmethod
    def _timed(task: Callable, seconds: float):
        return run_with_time_limit(task, seconds)
