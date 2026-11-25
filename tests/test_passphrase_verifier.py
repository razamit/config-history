"""The passphrase verifier catches typos before a push encrypts anything."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app
from claude_cfg.cli.encryption_prompts import EncryptionChoice, encryption_section
from claude_cfg.encryption import PassphraseCipher
from claude_cfg.errors import PassphraseMismatchError
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.passphrase_verifier import VERIFIER_KEY, create_verifier, verifier_matches
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files

TRACKED = {"storage": "local", "tracked": ["CLAUDE.md"]}


@pytest.fixture
def claude_home(isolated_home):
    write_files(isolated_home / ".claude", {"CLAUDE.md": "# mine"})
    return isolated_home / ".claude"


def _cfg_with_verifier(passphrase: str) -> dict:
    return {**TRACKED, "encryption": {"enabled": True, VERIFIER_KEY: create_verifier(passphrase)}}


def test_verifier_matches_only_its_passphrase_and_holds_no_secret():
    verifier = create_verifier("correct horse")
    assert verifier_matches(verifier, "correct horse") is True
    assert verifier_matches(verifier, "correct hose") is False
    assert "correct horse" not in str(verifier)
    assert verifier_matches({"log2_n": 30, "r": 8, "p": 1, "salt": "AA==", "hash": "AA=="}, "x") is None
    assert verifier_matches("junk", "x") is None


def test_verifier_is_not_a_key_that_opens_snapshots():
    envelope = PassphraseCipher("correct horse").encrypt(b"zip")
    verifier = create_verifier("correct horse")
    assert verifier["hash"].encode() not in envelope


def test_section_always_has_a_verifier_and_masks_it():
    for save in (True, False):
        section = encryption_section(EncryptionChoice("pw", save_passphrase=save))
        assert verifier_matches(section[VERIFIER_KEY], "pw") is True
        assert ("passphrase" in section) is save
    assert cfg_mod.masked({"encryption": section})["encryption"][VERIFIER_KEY] == "***"


def test_env_passphrase_that_does_not_match_stops_the_push(claude_home, monkeypatch):
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "typo")
    provider = MemoryProvider()
    with pytest.raises(PassphraseMismatchError, match="does not match the one set up on this machine"):
        core.push("x", _cfg_with_verifier("right"), provider)
    assert provider.list_keys("snapshots/") == []


def test_prompted_passphrase_is_checked_once_against_the_verifier(claude_home, monkeypatch):
    monkeypatch.setattr("claude_cfg.passphrase._stdin_is_tty", lambda: True)
    asked = []
    prompt = lambda: asked.append(1) or "right"  # noqa: E731
    pushed = core.push("x", _cfg_with_verifier("right"), MemoryProvider(), passphrase_prompt=prompt)
    assert pushed["encrypted"] is True and asked == [1]
    with pytest.raises(PassphraseMismatchError):
        core.push("x", _cfg_with_verifier("other"), MemoryProvider(), passphrase_prompt=prompt)


def test_without_a_verifier_two_different_answers_stop_the_push(claude_home, monkeypatch):
    monkeypatch.setattr("claude_cfg.passphrase._stdin_is_tty", lambda: True)
    answers = iter(["first", "second"])
    cfg = {**TRACKED, "encryption": {"enabled": True}}
    with pytest.raises(PassphraseMismatchError, match="do not match"):
        core.push("x", cfg, MemoryProvider(), passphrase_prompt=lambda: next(answers))


def test_config_encrypt_writes_the_verifier_even_when_not_saving_the_passphrase(claude_home):
    cfg_mod.save(dict(TRACKED))
    result = CliRunner().invoke(app, ["config", "encrypt"], input="pw\npw\nn\n")
    assert result.exit_code == 0, result.output
    section = cfg_mod.load()["encryption"]
    assert "passphrase" not in section
    assert verifier_matches(section[VERIFIER_KEY], "pw") is True
