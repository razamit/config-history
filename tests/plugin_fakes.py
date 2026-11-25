"""Fakes and helpers for the plugin bootstrap tests (scripts/config_history_*.py).

Every process is a fake: no test creates a virtual environment, runs pip or
starts a detached process. All paths live under pytest's tmp_path.
"""

import io
import json
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Keep bytecode out of the shipped scripts folder while importing it.
_previous_dont_write_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
import config_history_bootstrap as bootstrap  # noqa: E402
import config_history_hook  # noqa: E402,F401 - imported here so no bytecode is written
import config_history_install_records  # noqa: E402,F401
import config_history_installer  # noqa: E402,F401
from config_history_process import CommandResult  # noqa: E402
from config_history_state import resolve_paths, write_marker  # noqa: E402

sys.dont_write_bytecode = _previous_dont_write_bytecode

PLUGIN_VERSION = "0.3.0"
DAY_SECONDS = 24 * 60 * 60
HOUR_SECONDS = 60 * 60
CURRENT_ENVIRONMENT = "venv-1700000000"


class FakeClock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeRunner:
    """Records commands and answers them with a responder function."""

    def __init__(self, responder=None):
        self.calls = []
        self._responder = responder or (lambda args: CommandResult(0, "", ""))

    def run(self, args, env, timeout, cwd=None):
        self.calls.append({"args": list(args), "env": dict(env), "timeout": timeout, "cwd": cwd})
        return self._responder(list(args))


class FakeSpawner:
    def __init__(self, error=None):
        self.spawns = []
        self._error = error

    def spawn(self, args, env, log_file, cwd):
        if self._error:
            raise self._error
        self.spawns.append({"args": list(args), "env": dict(env), "log_file": log_file, "cwd": cwd})


class ExplodingRunner:
    def run(self, args, env, timeout, cwd=None):
        raise RuntimeError("boom")


def make_plugin_env(tmp_path):
    plugin_root = tmp_path / "plugin root with space"
    (plugin_root / ".claude-plugin").mkdir(parents=True)
    (plugin_root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "config-history", "version": PLUGIN_VERSION}))
    (plugin_root / "pyproject.toml").write_text("[project]\nname = 'claude-cfg'\n")
    (plugin_root / "claude_cfg").mkdir()
    (plugin_root / "claude_cfg" / "__init__.py").write_text("")
    (plugin_root / "scripts").mkdir()
    (plugin_root / "scripts" / "plugin-constraints.txt").write_text("typer==0.23.2\n")
    (plugin_root / "tests").mkdir()
    (plugin_root / "tests" / "test_x.py").write_text("")
    return {
        "HOME": str(tmp_path / "home"),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "CLAUDE_PLUGIN_DATA": str(tmp_path / "plugin data"),
        "PATH": "",
        "PYTHONPATH": "/should/be/removed",
    }


def paths_for(env):
    """The paths the bootstrap itself resolves on this system (Scripts\\python.exe on Windows)."""
    return resolve_paths(env, fallback_plugin_root="unused", is_windows=os.name == "nt")


def install_environment(env, marker_overrides=None, environment=CURRENT_ENVIRONMENT):
    """Create a fake environment Python and a marker, as a finished install would."""
    paths = paths_for(env)
    python = Path(paths.environment_python(environment))
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("")
    write_marker(paths, environment)
    if marker_overrides:
        marker = json.loads(Path(paths.marker_file).read_text())
        marker.update(marker_overrides)
        Path(paths.marker_file).write_text(json.dumps(marker))
    return paths


def run_main(env, event, runner=None, spawner=None, clock=None, find_executable=None):
    stdout = io.StringIO()
    exit_code = bootstrap.main(
        [event], env=env, stdout=stdout, runner=runner or FakeRunner(),
        spawner=spawner or FakeSpawner(), clock=clock or FakeClock(),
        find_executable=find_executable or (lambda name: None),
        base_python="/fake/base/python3")
    assert exit_code == 0
    return stdout.getvalue()


def system_message(output):
    lines = output.splitlines()
    assert len(lines) == 1, output
    return json.loads(lines[0])["systemMessage"]


def fake_install_responder(paths, observed, fail_on=None):
    """Simulate environment creation and record what the build copy looked like.

    ``fail_on`` names an argument (such as "pip") whose command fails.
    """
    def respond(args):
        if fail_on and fail_on in args:
            return CommandResult(1, "", "pip: no matching distribution")
        if "venv" in args:
            python = Path(paths.environment_python(Path(args[-1]).name))
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("")
        if "install" in args:
            staging = Path(paths.staging_dir)
            observed["staged_pyproject"] = (staging / "pyproject.toml").is_file()
            observed["staged_tests"] = (staging / "tests").exists()
            observed["install_args"] = list(args)
        return CommandResult(0, "", "")
    return respond
