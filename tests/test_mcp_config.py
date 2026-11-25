"""`config mcp` and the init question about MCP servers."""

import json

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app
from claude_cfg.config import is_mcp_sync_enabled
from claude_cfg.paths import config_file

runner = CliRunner()


@pytest.fixture
def plain_cfg(isolated_home):
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    return cfg


def test_off_by_default_for_existing_configs(plain_cfg):
    assert not is_mcp_sync_enabled(plain_cfg)
    assert is_mcp_sync_enabled({"mcp_servers": {"enabled": "true"}})
    assert "MCP server sync is off" in runner.invoke(app, ["config", "mcp"]).output


def test_enable_without_encryption_needs_confirmation(plain_cfg):
    declined = runner.invoke(app, ["config", "mcp", "--enable"], input="n\n")
    assert declined.exit_code == 1
    assert "plain text" in declined.output and "tokens" in declined.output
    assert not is_mcp_sync_enabled(cfg_mod.load())

    accepted = runner.invoke(app, ["config", "mcp", "--enable"], input="y\n")
    assert accepted.exit_code == 0 and is_mcp_sync_enabled(cfg_mod.load())

    disabled = runner.invoke(app, ["config", "mcp", "--disable"])
    assert disabled.exit_code == 0 and not is_mcp_sync_enabled(cfg_mod.load())


def test_enable_with_encryption_needs_no_confirmation(plain_cfg):
    cfg_mod.save({**plain_cfg, "encryption": {"enabled": True, "passphrase": "pw"}})
    result = runner.invoke(app, ["config", "mcp", "--enable"])
    assert result.exit_code == 0 and "plain text" not in result.output
    assert is_mcp_sync_enabled(cfg_mod.load())


@pytest.mark.parametrize(
    "answers, expected",
    [
        (["y", "pw", "pw", "y", ""], True),   # encrypted: blank answer means yes
        (["n", ""], False),                   # not encrypted: blank answer means no
    ],
)
def test_init_question_defaults_follow_encryption(isolated_home, answers, expected):
    (isolated_home / ".claude").mkdir()
    store = isolated_home / "store"
    result = runner.invoke(app, ["init"], input="\n".join(["local", str(store), "n", *answers]) + "\n")
    assert result.exit_code == 0, result.output
    assert "Sync user-level MCP servers? Their definitions often contain API tokens." in result.output
    assert json.loads(config_file().read_text())["mcp_servers"] == {"enabled": expected}
