"""The ``status --hook`` check that runs as a Claude Code SessionStart hook.

Contract: prints nothing unless the backend has a snapshot newer than what
this machine last synced, and then exactly one JSON object with a
``systemMessage``, which Claude Code shows to the user. It never raises,
never prompts, and gives up silently when the backend is slow, because
Claude's first response waits for SessionStart hooks.
"""

import json
import threading
from typing import Callable, Optional, TypeVar

from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.display_text import printable_text, shortened
from claude_cfg.program_name import program_name
from claude_cfg.sync_status import RemoteStatus

DEFAULT_TIME_LIMIT_SECONDS = 5.0
MACHINE_NAME_LIMIT = 40

ResultType = TypeVar("ResultType")


def run_with_time_limit(
    task: Callable[[], ResultType], time_limit_seconds: float
) -> Optional[ResultType]:
    """``task()`` run on a daemon thread; None when it raises or runs too long.

    The thread is a daemon, so a hung backend call cannot keep the process
    alive after the hook has given up on it.
    """
    outcome: dict[str, ResultType] = {}

    def run_task() -> None:
        try:
            outcome["value"] = task()
        except BaseException:  # noqa: BLE001 - the hook must stay silent
            pass

    worker = threading.Thread(target=run_task, name="claude-cfg-hook", daemon=True)
    worker.start()
    worker.join(time_limit_seconds)
    return outcome.get("value")


def safe_machine_name(machine: str) -> str:
    """A backend-supplied machine name, cleaned and capped for display.

    Anyone with write access to the backend chooses this text, and Claude
    Code shows it in its session, so it is kept short and on one line.
    """
    cleaned = shortened(printable_text(machine).strip(), MACHINE_NAME_LIMIT)
    return cleaned or "unknown"


def newer_snapshot_message(
    remote: RemoteStatus, wording: Optional[CommandWording] = None
) -> Optional[str]:
    """The one-line message, or None when nothing newer is known."""
    wording = wording or wording_for(None)
    latest = remote.latest
    if not remote.is_newer or latest is None or remote.error:
        return None
    date = printable_text(latest.timestamp.replace("T", " ").replace("Z", ""))[:16]
    message = (
        f"{program_name()}: {wording.version_noun(latest.snapshot_id)} from "
        f"{safe_machine_name(latest.machine)} ({date} UTC) is newer than this machine's last "
        f"sync. Run `{wording.command(wording.restore_verb)}` to get it."
    )
    return printable_text(message)


class SessionStartNoticeManager:
    """Builds the hook's stdout from an injected config loader and remote check."""

    def __init__(
        self,
        load_config: Callable[[], dict],
        check_remote_for: Callable[[dict], RemoteStatus],
        time_limit_seconds: float = DEFAULT_TIME_LIMIT_SECONDS,
    ) -> None:
        self._load_config = load_config
        self._check_remote_for = check_remote_for
        self._time_limit_seconds = time_limit_seconds

    def notice_json(self) -> Optional[str]:
        """``{"systemMessage": ...}`` as one line, or None to print nothing."""
        try:
            cfg = self._load_config()
            remote = run_with_time_limit(lambda: self._check_remote_for(cfg), self._time_limit_seconds)
            message = newer_snapshot_message(remote, wording_for(cfg)) if remote is not None else None
            return json.dumps({"systemMessage": message}) if message else None
        except BaseException:  # noqa: BLE001 - the hook must stay silent
            return None
