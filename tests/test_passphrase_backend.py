"""Every passphrase source is checked, and a machine with no verifier checks
its passphrase against the backend before storing one."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, config_commands
from claude_cfg.encryption import SCRYPT_LOG2_N
from claude_cfg.errors import PassphraseMismatchError
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR, PassphraseResolver
from claude_cfg.passphrase_verifier import VERIFIER_KEY, create_verifier, verifier_matches
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files

TRACKED = {"storage": "local", "tracked": ["CLAUDE.md"]}
NO_VERIFIER = {**TRACKED, "encryption": {"enabled": True}}


@pytest.fixture
def claude_home(isolated_home):
    write_files(isolated_home / ".claude", {"CLAUDE.md": "# mine"})
    return isolated_home / ".claude"


@pytest.fixture
def backend_with_snapshot(claude_home):
    """A backend holding one snapshot encrypted under "first"."""
    provider = MemoryProvider()
    core.push("one", {**TRACKED, "encryption": {"enabled": True, "passphrase": "first"}}, provider)
    return provider


def _saved_verifier():
    return cfg_mod.load().get("encryption", {}).get(VERIFIER_KEY)


def test_verifier_uses_the_snapshot_cost():
    assert create_verifier("pw")["log2_n"] == SCRYPT_LOG2_N


def test_a_saved_passphrase_is_checked_against_the_verifier_too():
    cfg = {"encryption": {"enabled": True, "passphrase": "typo", VERIFIER_KEY: create_verifier("right")}}
    resolver = PassphraseResolver(cfg, environ={}, check_before_push=True)
    with pytest.raises(PassphraseMismatchError, match="claude-cfg config encrypt"):
        resolver.resolve()


def test_push_without_verifier_refuses_a_passphrase_the_backend_does_not_accept(
    backend_with_snapshot, monkeypatch
):
    cfg_mod.save(NO_VERIFIER)
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "second")
    with pytest.raises(PassphraseMismatchError, match="does not open the existing snapshots"):
        core.push("two", NO_VERIFIER, backend_with_snapshot)
    assert len(backend_with_snapshot.list_keys("snapshots/")) == 1
    assert _saved_verifier() is None


def test_push_without_verifier_stores_one_once_the_backend_accepts_it(
    backend_with_snapshot, monkeypatch
):
    cfg_mod.save(NO_VERIFIER)
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "first")
    assert core.push("two", NO_VERIFIER, backend_with_snapshot)["id"] == 2
    assert verifier_matches(_saved_verifier(), "first") is True


def test_push_to_an_empty_backend_stores_the_verifier(claude_home, monkeypatch):
    cfg_mod.save(NO_VERIFIER)
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "fresh")
    core.push("one", NO_VERIFIER, MemoryProvider())
    assert verifier_matches(_saved_verifier(), "fresh") is True


def test_pull_that_decrypts_stores_the_verifier_but_a_dry_run_does_not(
    backend_with_snapshot, monkeypatch
):
    cfg_mod.save(NO_VERIFIER)
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "first")
    core.prepare_pull(None, NO_VERIFIER, backend_with_snapshot)
    assert _saved_verifier() is None
    core.pull(None, NO_VERIFIER, backend_with_snapshot)
    assert verifier_matches(_saved_verifier(), "first") is True


def _local_backend_cfg(store, provider: MemoryProvider) -> dict:
    for key, blob in provider._store.items():
        (store / key).parent.mkdir(parents=True, exist_ok=True)
        (store / key).write_bytes(blob)
    return {**TRACKED, "local": {"path": str(store)}}


def test_config_encrypt_stops_when_the_passphrase_does_not_open_the_backend(
    backend_with_snapshot, isolated_home
):
    cfg = _local_backend_cfg(isolated_home / "store", backend_with_snapshot)
    cfg_mod.save(cfg)
    result = CliRunner().invoke(app, ["config", "encrypt"], input="second\nsecond\ny\n")
    assert result.exit_code == 1
    assert "does not open the existing snapshots on this backend" in result.output
    assert "encryption" not in cfg_mod.load()
    accepted = CliRunner().invoke(app, ["config", "encrypt"], input="first\nfirst\ny\n")
    assert accepted.exit_code == 0, accepted.output
    assert verifier_matches(_saved_verifier(), "first") is True


def test_config_encrypt_warns_and_saves_when_the_backend_is_unreachable(claude_home, monkeypatch):
    cfg_mod.save(dict(TRACKED))

    def unreachable(cfg):
        raise ConnectionError("no route")

    monkeypatch.setattr(config_commands, "get_provider", unreachable)
    result = CliRunner().invoke(app, ["config", "encrypt"], input="pw\npw\ny\n")
    assert result.exit_code == 0, result.output
    assert "Could not check the passphrase" in result.output
    assert verifier_matches(_saved_verifier(), "pw") is True


def test_init_stops_when_the_passphrase_does_not_open_the_backend(backend_with_snapshot, isolated_home):
    store = isolated_home / "store"
    _local_backend_cfg(store, backend_with_snapshot)
    answers = ["local", str(store), "n", "y", "second", "second", "y"]
    result = CliRunner().invoke(app, ["init"], input="\n".join(answers) + "\n")
    assert result.exit_code == 1
    assert "does not open the existing snapshots on this backend" in result.output
    assert not cfg_mod.config_file().exists()
