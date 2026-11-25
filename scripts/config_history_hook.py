"""SessionStart and SessionEnd handling for the config-history plugin.

Stdlib only and compatible with Python 3.9. When the private environment is
installed and current, the hook runs the tool's session hook. Otherwise it
starts the install in the background, unless a failed install is backing
off, and keeps running the environment already in use, if there is one.
It prints at most one systemMessage line, so the session is never blocked.
"""

from __future__ import annotations

import json
from typing import Callable, List, Mapping, Optional

from config_history_install_records import InstallLock, InstallStatus
from config_history_process import session_hook_command, tool_environment
from config_history_state import (
    BootstrapPaths,
    Clock,
    install_target,
    installed_python,
    marker_matches,
    write_pointer_file,
)

SETUP_NOTICE = (
    "config-history is setting up for first use (about a minute). "
    "Your config history starts when it finishes."
)
UPDATE_NOTICE = (
    "config-history is updating after a plugin update (about a minute). "
    "The installed version keeps saving until the update is ready."
)
STILL_SETTING_UP_NOTICE = (
    "config-history is still setting up. Your config history starts when it finishes."
)
FAILURE_NOTICE = (
    "config-history could not finish setting up and tries again later in the background. "
    "Details: {log_file}"
)
UPDATE_FAILURE_NOTICE = (
    "config-history could not install its update and keeps using the installed version. "
    "It tries again later in the background. Details: {log_file}"
)
# The hook gets 15 s from Claude Code (hooks/hooks.json). The tool's own
# start hook gets 12 s of that, which leaves time for the shell launcher and
# this script. Inside the 12 s the tool spends at most 9 s on its remote
# check and auto-save (see claude_cfg/session_hook_manager.py).
START_HOOK_TIMEOUT_SECONDS = 12

TextSink = Callable[[str], None]


class HookBootstrap:
    """Decides what a SessionStart or SessionEnd hook does."""

    def __init__(self, paths: BootstrapPaths, runner, spawner, clock: Clock,
                 env: Mapping[str, str], emit: TextSink, log: TextSink,
                 install_command: List[str]):
        self._paths = paths
        self._runner = runner
        self._spawner = spawner
        self._clock = clock
        self._tool_env = tool_environment(env)
        self._emit = emit
        self._log = log
        self._install_command = install_command
        self._status = InstallStatus(paths.status_file)

    def handle(self, hook_event: str) -> None:
        if hook_event == "start":
            self._handle_start()
        elif hook_event == "end":
            self._handle_end()

    def _handle_start(self) -> None:
        python = installed_python(self._paths)
        if python is not None and marker_matches(self._paths):
            output = self._run_start_hook(python)
            if output:
                self._emit(output)
            return
        notice = self._schedule_install(has_installed=python is not None)
        tool_message = system_message_in(self._run_start_hook(python)) if python else None
        self._emit_messages([tool_message, notice])

    def _handle_end(self) -> None:
        """Run the end hook detached: plugin SessionEnd hooks get about 1.5 seconds."""
        python = installed_python(self._paths)
        if python is None:
            return
        command = session_hook_command(python, "end")
        self._spawner.spawn(command, self._tool_env, self._paths.log_file, self._paths.data_dir)

    def _run_start_hook(self, python: str) -> Optional[str]:
        """The tool's start hook output, or None when it failed."""
        self._refresh_pointer_file(python)
        command = session_hook_command(python, "start")
        result = self._runner.run(command, env=self._tool_env, timeout=START_HOOK_TIMEOUT_SECONDS)
        if result.succeeded:
            return result.stdout
        self._log("session-hook start failed (exit code {}): {}".format(
            result.returncode, result.stderr.strip()))
        return None

    def _refresh_pointer_file(self, python: str) -> None:
        try:
            write_pointer_file(self._paths, python)
        except OSError as error:
            self._log("could not write the pointer file: {}".format(error))

    def _schedule_install(self, has_installed: bool) -> Optional[str]:
        """Start the background install when allowed; return the notice for it."""
        now = self._clock()
        target = install_target(self._paths)
        if not self._status.install_allowed(now, target):
            return self._failure_notice(now, has_installed)
        lock = InstallLock(self._paths.lock_file, self._clock)
        if not lock.try_acquire():
            return None if has_installed else STILL_SETTING_UP_NOTICE
        notice = self._install_notice(now, has_installed)
        try:
            self._spawner.spawn(
                self._install_command, self._tool_env, self._paths.log_file, self._paths.data_dir)
        except OSError as error:
            lock.release()
            self._log("could not start the install: {}".format(error))
            self._status.record_failure("could not start the install: {}".format(error), now, target)
            return None
        return notice

    def _install_notice(self, now: float, has_installed: bool) -> Optional[str]:
        """Pick the one message for a started install, or None to stay quiet."""
        if self._status.has_failure():
            return self._failure_notice(now, has_installed)
        return UPDATE_NOTICE if has_installed else SETUP_NOTICE

    def _failure_notice(self, now: float, has_installed: bool) -> Optional[str]:
        """The failure notice, at most once per report interval (a day)."""
        if not self._status.should_report(now):
            return None
        self._status.mark_reported(now)
        template = UPDATE_FAILURE_NOTICE if has_installed else FAILURE_NOTICE
        return template.format(log_file=self._paths.log_file)

    def _emit_messages(self, messages: List[Optional[str]]) -> None:
        lines = [message for message in messages if message]
        if lines:
            self._emit(json.dumps({"systemMessage": "\n".join(lines)}) + "\n")


def system_message_in(output: Optional[str]) -> Optional[str]:
    """The systemMessage text in the tool's one-line JSON output, if any."""
    if not output or not output.strip():
        return None
    try:
        parsed = json.loads(output.strip().splitlines()[-1])
    except ValueError:
        return None
    message = parsed.get("systemMessage") if isinstance(parsed, dict) else None
    return message if isinstance(message, str) and message else None
