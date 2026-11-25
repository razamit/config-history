"""Plugin updates: the environment in use keeps working until a new one is ready.

Also covers the install back-off, the pointer file line endings, the tool
home rules and the time budgets. Every process is a fake.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugin_fakes import (
    CURRENT_ENVIRONMENT,
    DAY_SECONDS,
    CommandResult,
    HOUR_SECONDS,
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
import config_history_state as state  # noqa: E402
from config_history_install_records import (  # noqa: E402
    STALE_LOCK_SECONDS,
    InstallLock,
    retry_delay,
)
from config_history_installer import INSTALL_TIME_BUDGET_SECONDS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_bytecode_in_scripts(monkeypatch):
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


@pytest.fixture
def updated_plugin(tmp_path):
    """An environment built for 0.2.0, while the plugin is now 0.3.0."""
    env = make_plugin_env(tmp_path)
    paths = install_environment(env, marker_overrides={"version": "0.2.0"})
    state.write_pointer_file(paths, paths.environment_python(CURRENT_ENVIRONMENT))
    return env, paths


def failing_install(env, paths, clock):
    InstallLock(paths.lock_file, clock).try_acquire()
    runner = FakeRunner(fake_install_responder(paths, {}, fail_on="pip"))
    run_main(env, "install", runner=runner, clock=clock)


def test_failed_update_keeps_the_environment_in_use(updated_plugin):
    env, paths = updated_plugin
    old_python = paths.environment_python(CURRENT_ENVIRONMENT)
    marker_before = Path(paths.marker_file).read_text()
    failing_install(env, paths, FakeClock())
    assert Path(paths.marker_file).read_text() == marker_before
    assert Path(old_python).is_file()
    assert Path(paths.pointer_file).read_text() == old_python + "\n"
    assert not os.path.exists(paths.environment_dir("venv-1800000000")), "the partial build is gone"
    assert not os.path.exists(paths.lock_file)
    status = json.loads(Path(paths.status_file).read_text())
    assert status["state"] == "failed" and "pip" in status["reason"]
    assert "no matching distribution" in Path(paths.log_file).read_text()


def test_sessions_keep_saving_with_the_old_environment_while_backing_off(updated_plugin):
    env, paths = updated_plugin
    clock = FakeClock()
    failing_install(env, paths, clock)
    tool_output = '{"systemMessage": "config-history: saved version 4."}\n'
    runner = FakeRunner(lambda args: hook_result(tool_output))
    spawner = FakeSpawner()
    first = system_message(run_main(env, "start", runner=runner, spawner=spawner, clock=clock))
    assert first.splitlines() == ["config-history: saved version 4.",
                                  hook.UPDATE_FAILURE_NOTICE.format(log_file=paths.log_file)]
    assert spawner.spawns == [], "no new install while backing off"
    old_python = paths.environment_python(CURRENT_ENVIRONMENT)
    assert runner.calls[0]["args"][0] == old_python
    clock.now += 60
    again = run_main(env, "start", runner=FakeRunner(), spawner=spawner, clock=clock)
    assert again == "" and spawner.spawns == []
    end_spawner = FakeSpawner()
    run_main(env, "end", spawner=end_spawner, clock=clock)
    assert end_spawner.spawns[0]["args"][0] == old_python


def hook_result(stdout):
    return CommandResult(0, stdout, "")


def test_backoff_doubles_up_to_a_day_and_retries_after_it(updated_plugin):
    env, paths = updated_plugin
    clock = FakeClock()
    assert [retry_delay(count) for count in (1, 2, 3, 6, 40)] == [
        HOUR_SECONDS, 2 * HOUR_SECONDS, 4 * HOUR_SECONDS, DAY_SECONDS, DAY_SECONDS]
    failing_install(env, paths, clock)
    clock.now += HOUR_SECONDS
    spawner = FakeSpawner()
    run_main(env, "start", spawner=spawner, clock=clock)
    assert len(spawner.spawns) == 1, "tries again after an hour"
    failing_install(env, paths, clock)
    status = json.loads(Path(paths.status_file).read_text())
    assert status["failure_count"] == 2
    assert status["retry_after"] == clock.now + 2 * HOUR_SECONDS


def test_failure_notice_at_most_once_per_day_without_an_environment(tmp_path):
    env = make_plugin_env(tmp_path)
    paths, clock = paths_for(env), FakeClock()
    failing_install(env, paths, clock)
    first = run_main(env, "start", clock=clock)
    assert system_message(first) == hook.FAILURE_NOTICE.format(log_file=paths.log_file)
    for _ in range(3):
        clock.now += 2 * HOUR_SECONDS
        InstallLock(paths.lock_file, clock).release()
        assert run_main(env, "start", clock=clock) == ""
    clock.now += DAY_SECONDS
    InstallLock(paths.lock_file, clock).release()
    assert paths.log_file in system_message(run_main(env, "start", clock=clock))


def test_new_plugin_version_is_not_held_back_by_an_old_failure(updated_plugin):
    env, paths = updated_plugin
    clock = FakeClock()
    failing_install(env, paths, clock)
    manifest = Path(paths.manifest_file)
    manifest.write_text(json.dumps({"name": "config-history", "version": "0.3.1"}))
    spawner = FakeSpawner()
    run_main(env, "start", spawner=spawner, clock=clock)
    assert len(spawner.spawns) == 1


def test_successful_update_switches_and_keeps_only_the_previous_environment(updated_plugin):
    env, paths = updated_plugin
    older = Path(paths.environment_python("venv-1600000000"))
    older.parent.mkdir(parents=True)
    older.write_text("")
    run_main(env, "install", runner=FakeRunner(fake_install_responder(paths, {})))
    new_python = paths.environment_python("venv-1800000000")
    assert state.installed_python(paths) == new_python and state.marker_matches(paths)
    assert Path(paths.pointer_file).read_text() == new_python + "\n"
    assert Path(paths.environment_python(CURRENT_ENVIRONMENT)).is_file(), "previous is kept"
    assert not older.exists()


def test_legacy_marker_without_environment_uses_the_venv_folder(tmp_path):
    env = make_plugin_env(tmp_path)
    paths = install_environment(env, environment="venv")
    marker = json.loads(Path(paths.marker_file).read_text())
    del marker["environment"]
    Path(paths.marker_file).write_text(json.dumps(marker))
    assert state.installed_python(paths) == paths.environment_python("venv")
    assert state.marker_matches(paths)


@pytest.mark.parametrize("name", ["../outside", "/abs", "venv-1/../../x", 7])
def test_marker_cannot_name_a_folder_outside_the_data_folder(tmp_path, name):
    env = make_plugin_env(tmp_path)
    paths = install_environment(env, marker_overrides={"environment": name})
    assert state.installed_python(paths) is None


def test_pointer_file_has_unix_line_ending_under_windows_text_mode(tmp_path, monkeypatch):
    """Simulate Windows text mode: a newline argument of None writes CRLF."""
    real_fdopen = os.fdopen

    def windows_fdopen(descriptor, mode="r", *args, **kwargs):
        if "b" not in mode and kwargs.get("newline") is None:
            kwargs["newline"] = "\r\n"
        return real_fdopen(descriptor, mode, *args, **kwargs)

    monkeypatch.setattr(state.os, "fdopen", windows_fdopen)
    paths = paths_for(dict(make_plugin_env(tmp_path), CLAUDE_CFG_HOME=str(tmp_path / "tool")))
    state.write_pointer_file(paths, "C:/data/venv-1/Scripts/python.exe")
    assert Path(paths.pointer_file).read_bytes() == b"C:/data/venv-1/Scripts/python.exe\n"


@pytest.mark.parametrize("configured", ["relative/home", "~", "~/elsewhere", "./x", "C:relative"])
def test_tool_home_ignores_values_that_are_not_absolute(configured):
    home = state.resolve_tool_home({"HOME": "/home/me", "CLAUDE_CFG_HOME": configured})
    assert home == os.path.join("/home/me", ".claude-cfg")


@pytest.mark.parametrize("configured", ["/srv/tool home", "C:\\Users\\me\\tool", "\\\\server\\share\\t"])
def test_tool_home_accepts_absolute_values(configured):
    assert state.resolve_tool_home({"HOME": "/home/me", "CLAUDE_CFG_HOME": configured}) == configured


def test_install_lock_outlives_the_whole_install():
    assert STALE_LOCK_SECONDS > INSTALL_TIME_BUDGET_SECONDS


def test_start_hook_budgets_nest():
    from claude_cfg import session_hook_manager as manager

    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())
    hook_timeout = hooks["hooks"]["SessionStart"][0]["hooks"][0]["timeout"]
    tool_budget = (manager.REMOTE_TIME_LIMIT_SECONDS + manager.START_AUTOSAVE_TIME_LIMIT_SECONDS
                   + manager.STARTUP_ALLOWANCE_SECONDS)
    assert tool_budget <= hook.START_HOOK_TIMEOUT_SECONDS < hook_timeout
