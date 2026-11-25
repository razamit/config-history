"""CLI tests. Every test runs against the throwaway home from conftest."""

import json
import os
import platform

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app
from claude_cfg.cli import output
from claude_cfg.passphrase_verifier import VERIFIER_KEY, verifier_matches
from claude_cfg.paths import config_file

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def store_dir(isolated_home):
    return isolated_home / "store"


@pytest.fixture
def local_cfg(isolated_home, store_dir):
    claude = isolated_home / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# hi")
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(store_dir)}}
    cfg_mod.save(cfg)
    return cfg


def _without_verifier(section: dict, passphrase: str) -> dict:
    """The section minus its passphrase verifier, after checking the verifier."""
    rest = dict(section)
    assert verifier_matches(rest.pop(VERIFIER_KEY), passphrase) is True
    return rest


def _snapshot_files(store_dir) -> list[str]:
    return sorted(p.name for p in (store_dir / "snapshots").iterdir())


def test_masked_hides_passphrase():
    cfg = {"encryption": {"enabled": True, "passphrase": "hunter2"}}
    assert cfg_mod.masked(cfg)["encryption"] == {"enabled": True, "passphrase": "***"}


def test_config_show_masks_passphrase(local_cfg):
    cfg_mod.save({**local_cfg, "encryption": {"enabled": True, "passphrase": "hunter2"}})
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0, result.output
    assert "hunter2" not in result.output
    assert '"passphrase": "***"' in result.output


def test_config_encrypt_saves_passphrase_owner_only(local_cfg):
    result = runner.invoke(app, ["config", "encrypt"], input="pw\npw\ny\n")
    assert result.exit_code == 0, result.output
    assert _without_verifier(cfg_mod.load()["encryption"], "pw") == {"enabled": True, "passphrase": "pw"}
    if platform.system() != "Windows":
        assert oct(os.stat(config_file()).st_mode & 0o777) == "0o600"


def test_config_encrypt_without_saving_passphrase(local_cfg):
    result = runner.invoke(app, ["config", "encrypt"], input="pw\npw\nn\n")
    assert result.exit_code == 0, result.output
    assert _without_verifier(cfg_mod.load()["encryption"], "pw") == {"enabled": True}
    assert "CLAUDE_CFG_PASSPHRASE" in result.output


def test_unencrypted_push_prints_notice(local_cfg, store_dir):
    result = runner.invoke(app, ["push", "first"])
    assert result.exit_code == 0, result.output
    assert "not encrypted" in result.output
    assert "claude-cfg config encrypt" in result.output
    assert _snapshot_files(store_dir)[0].endswith(".zip")


def test_pull_by_key_and_duplicate_id_error(local_cfg, store_dir):
    runner.invoke(app, ["push", "one"])
    original = _snapshot_files(store_dir)[0]
    duplicate = original.replace("_one_", "_two_")
    (store_dir / "snapshots" / duplicate).write_bytes(
        (store_dir / "snapshots" / original).read_bytes()
    )

    listed = runner.invoke(app, ["list", "--keys"])
    assert original in listed.output and duplicate in listed.output

    ambiguous = runner.invoke(app, ["pull", "--point", "1"])
    assert ambiguous.exit_code == 1
    assert "--key" in ambiguous.output and duplicate in ambiguous.output

    chosen = runner.invoke(app, ["pull", "--key", f"snapshots/{duplicate}"])
    assert chosen.exit_code == 0, chosen.output
    assert "Snapshot #1 restored" in chosen.output


def test_pull_rejects_point_and_key_together(local_cfg):
    result = runner.invoke(app, ["pull", "--point", "1", "--key", "snapshots/x.zip"])
    assert result.exit_code == 1
    assert "either --point or --key" in result.output


def test_init_local_with_encryption_pushes_encrypted_snapshot(isolated_home, store_dir):
    claude = isolated_home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}")
    answers = [
        "local",          # backend
        str(store_dir),   # folder path
        "n",              # customize tracked files
        "y",              # encrypt snapshots
        "pw", "pw",       # passphrase and confirmation
        "y",              # save passphrase
        "n",              # sync MCP servers
    ]
    result = runner.invoke(app, ["init"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output

    saved = json.loads(config_file().read_text())
    assert _without_verifier(saved["encryption"], "pw") == {"enabled": True, "passphrase": "pw"}
    files = _snapshot_files(store_dir)
    assert len(files) == 1 and files[0].endswith(".zip.enc")
    assert "not encrypted" not in result.output


def test_init_without_saved_passphrase_still_pushes_encrypted(isolated_home, store_dir):
    (isolated_home / ".claude").mkdir()
    answers = ["local", str(store_dir), "n", "y", "pw", "pw", "n", ""]
    result = runner.invoke(app, ["init"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert _without_verifier(json.loads(config_file().read_text())["encryption"], "pw") == {"enabled": True}
    assert _snapshot_files(store_dir)[0].endswith(".zip.enc")


def test_help_lists_new_options():
    assert "--key" in runner.invoke(app, ["pull", "--help"]).output
    assert "--keys" in runner.invoke(app, ["list", "--help"]).output
    assert "encrypt" in runner.invoke(app, ["config", "--help"]).output


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("claude-cfg ")
