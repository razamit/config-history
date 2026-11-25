"""Tests for the plugin hook bootstrap (scripts/config_history_*.py).

Every process is a fake: no test creates a virtual environment, runs pip or
starts a detached process. All paths live under pytest's tmp_path. Updates,
failed installs and back-off are in test_plugin_update.py.
"""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tests.plugin_fakes import (
    CURRENT_ENVIRONMENT,
    PLUGIN_VERSION,
    CommandResult,
    ExplodingRunner,
    FakeClock,
    FakeRunner,
    FakeSpawner,
    fake_install_responder,
    install_environment,
    make_plugin_env,
    paths_for,
    run_main,
    system_message,
)
import config_history_hook as hook  # noqa: E402
from config_history_install_records import STALE_LOCK_SECONDS, InstallLock  # noqa: E402


@pytest.fixture(autouse=True)
def no_bytecode_in_scripts(monkeypatch):
    """The bootstrap imports modules lazily; keep their bytecode out of scripts/."""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


@pytest.fixture
def plugin_env(tmp_path):
    return make_plugin_env(tmp_path)


# Start hook with a current install

def test_marker_match_runs_start_hook_and_passes_stdout_through(plugin_env):
    paths = install_environment(plugin_env)
    tool_output = '{"systemMessage": "Saved version 4."}\n'
    runner = FakeRunner(lambda args: CommandResult(0, tool_output, ""))
    spawner = FakeSpawner()
    output = run_main(plugin_env, "start", runner=runner, spawner=spawner)
    assert output == tool_output
    assert spawner.spawns == []
    call = runner.calls[0]
    python = paths.environment_python(CURRENT_ENVIRONMENT)
    assert call["args"] == [python, "-I", "-m", "claude_cfg", "session-hook", "start"]
    assert call["env"]["CLAUDE_CFG_PROGRAM_NAME"] == "config-history"
    assert "PYTHONPATH" not in call["env"]


def test_marker_match_with_silent_tool_prints_nothing(plugin_env):
    install_environment(plugin_env)
    assert run_main(plugin_env, "start") == ""


def test_failing_start_hook_prints_nothing_and_logs(plugin_env):
    paths = install_environment(plugin_env)
    runner = FakeRunner(lambda args: CommandResult(1, "partial", "Traceback: broken"))
    assert run_main(plugin_env, "start", runner=runner) == ""
    assert "broken" in Path(paths.log_file).read_text()


posix_modes_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no POSIX permission bits, so mode 0o600 does not exist there")


def test_start_writes_pointer_file_in_tool_home(plugin_env, tmp_path):
    plugin_env["CLAUDE_CFG_HOME"] = str(tmp_path / "tool home")
    paths = install_environment(plugin_env)
    run_main(plugin_env, "start")
    pointer = tmp_path / "tool home" / "plugin-python"
    assert pointer.read_bytes() == (paths.environment_python(CURRENT_ENVIRONMENT) + "\n").encode()


@posix_modes_only
def test_start_writes_owner_only_pointer_file(plugin_env):
    paths = install_environment(plugin_env)
    run_main(plugin_env, "start")
    assert stat.S_IMODE(Path(paths.pointer_file).stat().st_mode) == 0o600


def test_pointer_file_defaults_to_home_claude_cfg(plugin_env):
    install_environment(plugin_env)
    run_main(plugin_env, "start")
    assert (Path(plugin_env["HOME"]) / ".claude-cfg" / "plugin-python").is_file()


# Start hook without a current install

def test_missing_venv_starts_background_install_with_setup_notice(plugin_env):
    runner, spawner = FakeRunner(), FakeSpawner()
    output = run_main(plugin_env, "start", runner=runner, spawner=spawner)
    assert system_message(output) == hook.SETUP_NOTICE
    assert runner.calls == []
    assert len(spawner.spawns) == 1
    spawn = spawner.spawns[0]
    assert spawn["args"][0] == "/fake/base/python3"
    assert spawn["args"][-1] == "install"
    assert spawn["args"][-2].endswith("config_history_bootstrap.py")
    assert spawn["log_file"] == paths_for(plugin_env).log_file
    assert os.path.exists(paths_for(plugin_env).lock_file)


def test_start_while_install_runs_does_not_start_a_second_one(plugin_env):
    clock = FakeClock()
    run_main(plugin_env, "start", clock=clock)
    spawner = FakeSpawner()
    clock.now += 30
    output = run_main(plugin_env, "start", spawner=spawner, clock=clock)
    assert spawner.spawns == []
    assert system_message(output) == hook.STILL_SETTING_UP_NOTICE


def test_stale_lock_is_replaced(plugin_env):
    clock = FakeClock()
    run_main(plugin_env, "start", clock=clock)
    clock.now += STALE_LOCK_SECONDS + 60
    spawner = FakeSpawner()
    output = run_main(plugin_env, "start", spawner=spawner, clock=clock)
    assert len(spawner.spawns) == 1
    assert system_message(output) == hook.SETUP_NOTICE


@pytest.mark.parametrize("changed", [{"version": "0.2.0"}, {"plugin_root": "/old/cache/0.2.0"}])
def test_version_or_root_change_triggers_reinstall(plugin_env, changed):
    paths = install_environment(plugin_env, marker_overrides=changed)
    runner, spawner = FakeRunner(), FakeSpawner()
    output = run_main(plugin_env, "start", runner=runner, spawner=spawner)
    assert len(spawner.spawns) == 1
    assert system_message(output) == hook.UPDATE_NOTICE
    old_python = paths.environment_python(CURRENT_ENVIRONMENT)
    assert [call["args"][0] for call in runner.calls] == [old_python], "the old one keeps saving"


def test_spawn_failure_releases_lock_and_records_failure(plugin_env):
    paths = paths_for(plugin_env)
    output = run_main(plugin_env, "start", spawner=FakeSpawner(error=OSError("no fork")))
    assert output == ""
    assert not os.path.exists(paths.lock_file)
    assert json.loads(Path(paths.status_file).read_text())["state"] == "failed"


# End hook

def test_end_without_venv_does_nothing(plugin_env):
    runner, spawner = FakeRunner(), FakeSpawner()
    assert run_main(plugin_env, "end", runner=runner, spawner=spawner) == ""
    assert runner.calls == [] and spawner.spawns == []
    assert not os.path.exists(plugin_env["CLAUDE_PLUGIN_DATA"])


def test_end_with_current_install_runs_end_hook_detached(plugin_env):
    paths = install_environment(plugin_env)
    runner, spawner = FakeRunner(), FakeSpawner()
    assert run_main(plugin_env, "end", runner=runner, spawner=spawner) == ""
    assert runner.calls == []
    spawn = spawner.spawns[0]
    python = paths.environment_python(CURRENT_ENVIRONMENT)
    assert spawn["args"] == [python, "-I", "-m", "claude_cfg", "session-hook", "end"]
    assert spawn["env"]["CLAUDE_CFG_PROGRAM_NAME"] == "config-history"


# Robustness

def test_unexpected_exception_exits_zero_prints_nothing_and_logs(plugin_env):
    paths = install_environment(plugin_env)
    assert run_main(plugin_env, "start", runner=ExplodingRunner()) == ""
    log_text = Path(paths.log_file).read_text()
    assert "unexpected error" in log_text and "RuntimeError: boom" in log_text


def test_missing_plugin_data_does_nothing(plugin_env):
    del plugin_env["CLAUDE_PLUGIN_DATA"]
    spawner = FakeSpawner()
    assert run_main(plugin_env, "start", spawner=spawner) == ""
    assert spawner.spawns == []


def test_unknown_event_does_nothing(plugin_env):
    spawner = FakeSpawner()
    assert run_main(plugin_env, "bogus", spawner=spawner) == ""
    assert spawner.spawns == []


# Background install

def test_install_with_pip_writes_marker_pointer_and_saves_first_version(plugin_env):
    paths = paths_for(plugin_env)
    InstallLock(paths.lock_file, FakeClock()).try_acquire()
    observed = {}
    runner = FakeRunner(fake_install_responder(paths, observed))
    assert run_main(plugin_env, "install", runner=runner) == ""
    commands = [call["args"] for call in runner.calls]
    environment = "venv-1800000000"
    python = paths.environment_python(environment)
    assert commands[0] == ["/fake/base/python3", "-I", "-m", "venv", paths.environment_dir(environment)]
    assert commands[1][:4] == [python, "-I", "-m", "pip"]
    constraints = os.path.join(paths.staging_dir, "scripts", "plugin-constraints.txt")
    assert commands[1][-3:] == ["--constraint", constraints, paths.staging_dir]
    assert commands[2] == [python, "-I", "-m", "claude_cfg", "session-hook", "start"]
    assert observed["staged_pyproject"] and not observed["staged_tests"]
    assert json.loads(Path(paths.marker_file).read_text()) == {
        "version": PLUGIN_VERSION, "plugin_root": paths.plugin_root, "environment": environment}
    assert Path(paths.pointer_file).read_text() == python + "\n"
    assert not os.path.exists(paths.lock_file)
    assert not os.path.exists(paths.staging_dir)
    assert run_main(plugin_env, "start") == "", "the next start uses the new install"


@posix_modes_only
def test_install_writes_owner_only_pointer_file(plugin_env):
    paths = paths_for(plugin_env)
    run_main(plugin_env, "install", runner=FakeRunner(fake_install_responder(paths, {})))
    assert stat.S_IMODE(Path(paths.pointer_file).stat().st_mode) == 0o600


def test_install_uses_uv_when_available(plugin_env):
    paths = paths_for(plugin_env)
    runner = FakeRunner(fake_install_responder(paths, {}))
    run_main(plugin_env, "install", runner=runner, find_executable=lambda name: "/fake/bin/uv")
    commands = [call["args"] for call in runner.calls]
    environment = "venv-1800000000"
    assert commands[0] == ["/fake/bin/uv", "venv", "--python", "/fake/base/python3",
                           paths.environment_dir(environment)]
    constraints = os.path.join(paths.staging_dir, "scripts", "plugin-constraints.txt")
    assert commands[1] == ["/fake/bin/uv", "pip", "install", "--python",
                           paths.environment_python(environment), "--constraint", constraints,
                           paths.staging_dir]


def test_successful_install_clears_previous_failure(plugin_env):
    paths = paths_for(plugin_env)
    run_main(plugin_env, "install", runner=FakeRunner(lambda args: CommandResult(1, "", "")))
    assert os.path.exists(paths.status_file)
    run_main(plugin_env, "install", runner=FakeRunner(fake_install_responder(paths, {})))
    assert not os.path.exists(paths.status_file)


def test_lock_refuses_second_holder_until_stale(tmp_path):
    clock = FakeClock()
    lock_file = str(tmp_path / "data" / "install.lock")
    assert InstallLock(lock_file, clock).try_acquire()
    assert not InstallLock(lock_file, clock).try_acquire()
    assert InstallLock(lock_file, clock).is_held()
    clock.now += STALE_LOCK_SECONDS
    assert not InstallLock(lock_file, clock).is_held()
    assert InstallLock(lock_file, clock).try_acquire()
