"""Background installer for the config-history plugin.

Stdlib only and compatible with Python 3.9. Builds a new private virtual
environment beside the one in use, installs the claude_cfg package from a
copy of the plugin root with the pinned versions in
scripts/plugin-constraints.txt, and only then switches the marker and the
pointer file to it. Until that switch the existing environment keeps
working; a failed build is deleted and leaves it untouched. The command
runner, clock and executable lookup are injected so tests never create a
real environment or run pip.
"""

from __future__ import annotations

import os
import shutil
from typing import Callable, List, Mapping, Optional, Sequence

from config_history_install_records import InstallStatus
from config_history_process import CommandResult, session_hook_command, tool_environment
from config_history_state import (
    BootstrapPaths,
    Clock,
    install_target,
    installed_environment,
    new_environment_name,
    remove_environments_except,
    write_marker,
    write_pointer_file,
)

# Together 22 minutes, below the 30-minute stale time of the install lock
# (STALE_LOCK_SECONDS in config_history_install_records.py).
VENV_TIMEOUT_SECONDS = 300
PIP_TIMEOUT_SECONDS = 900
FIRST_SAVE_TIMEOUT_SECONDS = 120
INSTALL_TIME_BUDGET_SECONDS = VENV_TIMEOUT_SECONDS + PIP_TIMEOUT_SECONDS + FIRST_SAVE_TIMEOUT_SECONDS
CONSTRAINTS_FILE = os.path.join("scripts", "plugin-constraints.txt")

# Folders left out of the build copy: version control, local environments,
# build output and tests. The package build only needs the source and metadata.
_STAGING_IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "build", "dist", "*.egg-info", "__pycache__",
    ".pytest_cache", "tests", "node_modules",
)

ExecutableFinder = Callable[[str], Optional[str]]
LogWriter = Callable[[str], None]


class InstallError(Exception):
    """An install step failed; the message is the reason shown to the user."""


class PluginInstaller:
    """Creates the venv, installs the package and records the result."""

    def __init__(self, paths: BootstrapPaths, runner, env: Mapping[str, str], clock: Clock,
                 base_python: str, find_executable: ExecutableFinder, log: LogWriter):
        self._paths = paths
        self._runner = runner
        self._env = tool_environment(env)
        self._clock = clock
        self._base_python = base_python
        self._find_executable = find_executable
        self._log = log
        self._status = InstallStatus(paths.status_file)

    def install(self) -> bool:
        """Run the whole install. Returns True on success."""
        previous = installed_environment(self._paths)
        environment = new_environment_name(self._clock())
        try:
            self._build_environment(environment)
        except InstallError as error:
            self._log("install failed, the environment in use is unchanged: {}".format(error))
            self._status.record_failure(str(error), self._clock(), install_target(self._paths))
            shutil.rmtree(self._paths.environment_dir(environment), ignore_errors=True)
            return False
        finally:
            shutil.rmtree(self._paths.staging_dir, ignore_errors=True)
        self._switch_to(environment, previous)
        self._status.clear()
        self._log("install finished")
        self._save_first_version(environment)
        return True

    def _switch_to(self, environment: str, previous: Optional[str]) -> None:
        """Point the marker and the wrapper at the new environment.

        The previous one stays until the next install, since a process
        started from it may still be running.
        """
        write_marker(self._paths, environment)
        write_pointer_file(self._paths, self._paths.environment_python(environment))
        remove_environments_except(self._paths, (environment, previous))

    def _build_environment(self, environment: str) -> None:
        self._stage_source()
        uv_path = self._find_executable("uv")
        shutil.rmtree(self._paths.environment_dir(environment), ignore_errors=True)
        if uv_path:
            self._run_step("create the environment with uv",
                           self._uv_venv_command(uv_path, environment), VENV_TIMEOUT_SECONDS)
            self._run_step("install the package with uv",
                           self._uv_install_command(uv_path, environment), PIP_TIMEOUT_SECONDS)
        else:
            self._run_step("create the environment", self._venv_command(environment), VENV_TIMEOUT_SECONDS)
            self._run_step("install the package with pip",
                           self._pip_install_command(environment), PIP_TIMEOUT_SECONDS)

    def _stage_source(self) -> None:
        """Copy the plugin root so the build never writes into the plugin folder."""
        shutil.rmtree(self._paths.staging_dir, ignore_errors=True)
        try:
            shutil.copytree(self._paths.plugin_root, self._paths.staging_dir, ignore=_STAGING_IGNORE)
        except (OSError, shutil.Error) as error:
            raise InstallError("could not copy the plugin source: {}".format(error))

    def _run_step(self, description: str, args: List[str], timeout: float) -> CommandResult:
        self._log("{}: {}".format(description, " ".join(args)))
        result = self._runner.run(args, env=self._env, timeout=timeout, cwd=self._paths.data_dir)
        self._log_output(result)
        if not result.succeeded:
            raise InstallError("could not {} (exit code {})".format(description, result.returncode))
        return result

    def _log_output(self, result: CommandResult) -> None:
        for stream_text in (result.stdout, result.stderr):
            if stream_text.strip():
                self._log(stream_text.rstrip())

    def _constraint_arguments(self) -> List[str]:
        constraints = os.path.join(self._paths.staging_dir, CONSTRAINTS_FILE)
        if os.path.isfile(constraints):
            return ["--constraint", constraints]
        self._log("no constraints file at {}, installing without pinned versions".format(constraints))
        return []

    def _uv_venv_command(self, uv_path: str, environment: str) -> List[str]:
        return [uv_path, "venv", "--python", self._base_python, self._paths.environment_dir(environment)]

    def _uv_install_command(self, uv_path: str, environment: str) -> List[str]:
        return ([uv_path, "pip", "install", "--python", self._paths.environment_python(environment)]
                + self._constraint_arguments() + [self._paths.staging_dir])

    def _venv_command(self, environment: str) -> List[str]:
        return [self._base_python, "-I", "-m", "venv", self._paths.environment_dir(environment)]

    def _pip_install_command(self, environment: str) -> List[str]:
        return ([self._paths.environment_python(environment), "-I", "-m", "pip", "install",
                 "--disable-pip-version-check", "--no-input"]
                + self._constraint_arguments() + [self._paths.staging_dir])

    def _save_first_version(self, environment: str) -> None:
        """Run the start hook once so the first version is saved right away."""
        python = self._paths.environment_python(environment)
        args: Sequence[str] = session_hook_command(python, "start")
        result = self._runner.run(args, env=self._env, timeout=FIRST_SAVE_TIMEOUT_SECONDS)
        if not result.succeeded:
            self._log("first save failed (exit code {})".format(result.returncode))
            self._log_output(result)
