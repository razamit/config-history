"""Entry point for the config-history plugin hooks.

Usage: config_history_bootstrap.py start|end|install

Stdlib only and compatible with Python 3.9. "start" and "end" are called by the
hook launcher. "install" is the detached background install that "start"
launches. Every path exits 0 and prints nothing except an optional single JSON
line; an unexpected error goes to the install log instead.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import traceback
from typing import Callable, List, Mapping, Optional, TextIO

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_NAME = "install.log"
MAX_LOG_BYTES = 1_000_000


def append_log_line(log_file: str, clock: Callable[[], float], message: str) -> None:
    """Append a timestamped line to the log, starting over when it grows large."""
    try:
        os.makedirs(os.path.dirname(log_file), mode=0o700, exist_ok=True)
        if os.path.exists(log_file) and os.path.getsize(log_file) > MAX_LOG_BYTES:
            os.replace(log_file, log_file + ".old")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(clock()))
        descriptor = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write("[{}] {}\n".format(stamp, message))
    except OSError:
        pass


def installer_command(base_python: str) -> List[str]:
    return [base_python, "-B", "-E", "-s", os.path.join(SCRIPT_DIR, "config_history_bootstrap.py"), "install"]


def run_bootstrap(argv: List[str], env: Mapping[str, str], stdout: TextIO, runner, spawner,
                  clock: Callable[[], float], find_executable, base_python: str) -> None:
    """Resolve paths and dispatch to the hook handler or the installer."""
    from config_history_state import resolve_paths

    paths = resolve_paths(env, os.path.dirname(SCRIPT_DIR), is_windows=os.name == "nt")
    if paths is None:
        return
    hook_event = argv[0] if argv else "start"

    def log(message: str) -> None:
        append_log_line(paths.log_file, clock, message)

    if hook_event == "install":
        _run_install(paths, runner, env, clock, base_python, find_executable, log)
        return
    from config_history_hook import HookBootstrap

    def emit(text: str) -> None:
        stdout.write(text)
        stdout.flush()

    HookBootstrap(paths, runner, spawner, clock, env, emit, log,
                  installer_command(base_python)).handle(hook_event)


def _run_install(paths, runner, env, clock, base_python, find_executable, log) -> None:
    from config_history_installer import PluginInstaller
    from config_history_install_records import InstallLock

    lock = InstallLock(paths.lock_file, clock)
    try:
        PluginInstaller(paths, runner, env, clock, base_python, find_executable, log).install()
    finally:
        lock.release()


def _log_unexpected_error(env: Mapping[str, str]) -> None:
    data_dir = env.get("CLAUDE_PLUGIN_DATA", "").strip()
    if data_dir:
        append_log_line(os.path.join(data_dir, LOG_FILE_NAME), time.time,
                        "unexpected error:\n" + traceback.format_exc())


def main(argv: Optional[List[str]] = None, env: Optional[Mapping[str, str]] = None,
         stdout: Optional[TextIO] = None, runner=None, spawner=None,
         clock: Optional[Callable[[], float]] = None, find_executable=None,
         base_python: Optional[str] = None) -> int:
    """Run the bootstrap. Always returns 0."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    environment = dict(os.environ if env is None else env)
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        from config_history_process import DetachedSpawner, SubprocessRunner

        run_bootstrap(
            arguments, environment, stdout or sys.stdout,
            runner or SubprocessRunner(), spawner or DetachedSpawner(),
            clock or time.time,
            find_executable or (lambda name: shutil.which(name, path=environment.get("PATH"))),
            base_python or sys.executable,
        )
    except BaseException:  # noqa: BLE001 - a hook must never fail the session
        _log_unexpected_error(environment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
