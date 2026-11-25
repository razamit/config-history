"""`claude-cfg status --hook`: silent unless the backend has newer, always exit 0."""

import json
import socket
import time

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, status_command
from claude_cfg.paths import claude_dir
from claude_cfg.providers import get_provider
from claude_cfg.session_start_notice import SessionStartNoticeManager, run_with_time_limit
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, write_files

runner = CliRunner()


@pytest.fixture
def cfg(isolated_home):
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    core.push("one", cfg, get_provider(cfg))
    return cfg


def _hook():
    return runner.invoke(app, ["status", "--hook"])


def test_remote_newer_prints_one_system_message(cfg, tmp_path):
    other = tmp_path / "other"
    write_files(other, {"CLAUDE.md": "# other"})
    push_from_other_machine(get_provider(cfg), other, ["CLAUDE.md"], "from laptop")
    result = _hook()
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert len(lines) == 1
    document = json.loads(lines[0])
    assert list(document) == ["systemMessage"]
    message = document["systemMessage"]
    assert "#2" in message and socket.gethostname() in message and "claude-cfg pull" in message
    assert "\n" not in message


def test_up_to_date_prints_nothing(cfg):
    result = _hook()
    assert result.exit_code == 0 and result.output == ""


def test_no_config_prints_nothing(isolated_home):
    result = _hook()
    assert result.exit_code == 0 and result.output == ""


def test_raising_provider_prints_nothing(cfg, monkeypatch):
    def broken_provider(_cfg):
        raise ConnectionError("backend down")

    monkeypatch.setattr(status_command, "get_provider", broken_provider)
    result = _hook()
    assert result.exit_code == 0 and result.output == ""


class SlowProvider(MemoryProvider):
    def list_keys(self, prefix: str = "") -> list[str]:
        time.sleep(3)
        return []


def test_slow_provider_gives_up_silently(cfg, monkeypatch):
    monkeypatch.setattr(status_command, "get_provider", lambda _cfg: SlowProvider())
    monkeypatch.setattr(status_command, "HOOK_TIME_LIMIT_SECONDS", 0.2)
    started = time.monotonic()
    result = _hook()
    assert result.exit_code == 0 and result.output == ""
    assert time.monotonic() - started < 2


def test_manager_swallows_config_errors():
    def missing_config():
        raise FileNotFoundError("no config")

    manager = SessionStartNoticeManager(missing_config, lambda cfg: None)
    assert manager.notice_json() is None


def test_time_limit_returns_value_or_none():
    assert run_with_time_limit(lambda: 7, 1) == 7
    assert run_with_time_limit(lambda: 1 / 0, 1) is None
    assert run_with_time_limit(lambda: time.sleep(2), 0.05) is None
