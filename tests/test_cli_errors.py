"""Every failure ends as one error line, never a traceback with locals."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, output
from claude_cfg.cli.config_commands import config_app
from claude_cfg.cli.integrate_commands import integrate_app

runner = CliRunner()
SECRET = "tok-should-never-print"


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def saved_config(isolated_home):
    (isolated_home / ".claude").mkdir()
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(isolated_home / "s")},
           "gist": {"token": SECRET}}
    cfg_mod.save(cfg)
    return cfg


def _explode(*args, **kwargs):
    config_in_scope = {"token": SECRET}  # a local a traceback with locals would print
    raise RuntimeError(f"backend said no ({len(config_in_scope)})")


def test_every_typer_app_hides_locals():
    for typer_app in (app, config_app, integrate_app):
        assert typer_app.pretty_exceptions_show_locals is False


def test_unexpected_error_is_one_line_with_its_type(saved_config, monkeypatch):
    monkeypatch.setattr(core, "list_snapshots", _explode)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "RuntimeError: backend said no (1)" in result.output
    assert "Traceback" not in result.output and SECRET not in result.output
    assert not isinstance(result.exception, RuntimeError)


def test_commands_without_their_own_handler_are_covered_too(isolated_home):
    result = runner.invoke(app, ["config", "set", "storage", "local"])
    assert result.exit_code == 1
    assert "FileNotFoundError: Config not found" in result.output
    assert "Traceback" not in result.output


def test_debug_env_var_shows_a_traceback_without_locals(saved_config, monkeypatch):
    monkeypatch.setenv("CLAUDE_CFG_DEBUG", "1")
    monkeypatch.setattr(core, "list_snapshots", _explode)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Traceback" in result.output and "_explode" in result.output
    assert SECRET not in result.output


def test_usage_errors_still_come_from_typer(saved_config):
    result = runner.invoke(app, ["pull", "--no-such-flag"])
    assert result.exit_code == 2
