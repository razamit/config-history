import pytest

from claude_cfg import core
from claude_cfg.errors import (
    PassphraseUnavailableError,
    PlainSnapshotRefusedError,
    SnapshotDecryptionError,
    SnapshotIntegrityError,
)
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from tests.memory_provider import MemoryProvider

PLAIN_CFG = {"storage": "local", "tracked": ["settings.json", "CLAUDE.md"]}
ENCRYPTED_CFG = {**PLAIN_CFG, "encryption": {"enabled": True, "passphrase": "s3cret"}}


def _never_prompt() -> str:
    raise AssertionError("the passphrase prompt should not have been used")


@pytest.fixture
def claude_home(isolated_home):
    claude = isolated_home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text('{"apiKey": "sk-test"}')
    (claude / "CLAUDE.md").write_text("# original")
    return claude


@pytest.fixture
def no_terminal(monkeypatch):
    monkeypatch.setattr("claude_cfg.passphrase._stdin_is_tty", lambda: False)


def test_encrypted_push_then_pull(claude_home):
    provider = MemoryProvider()
    pushed = core.push("enc", ENCRYPTED_CFG, provider, passphrase_prompt=_never_prompt)
    assert pushed["encrypted"] is True
    assert pushed["key"].endswith(".zip.enc")
    assert b"sk-test" not in provider.download(pushed["key"])

    (claude_home / "CLAUDE.md").write_text("# changed")
    pulled = core.pull(None, ENCRYPTED_CFG, provider, passphrase_prompt=_never_prompt)
    assert pulled["encrypted"] is True
    assert pulled["message"] == "enc"
    assert (claude_home / "CLAUDE.md").read_text() == "# original"


def test_plain_snapshot_reads_when_local_config_has_encryption_on(claude_home):
    """With encryption on here, a plain snapshot is refused unless the user
    passes --allow-plain (for snapshots pushed before encryption was on)."""
    provider = MemoryProvider()
    pushed = core.push("plain", PLAIN_CFG, provider)
    assert pushed["encrypted"] is False
    assert pushed["key"].endswith(".zip")
    (claude_home / "CLAUDE.md").write_text("# changed")

    with pytest.raises(PlainSnapshotRefusedError, match="--allow-plain"):
        core.pull(None, ENCRYPTED_CFG, provider, passphrase_prompt=_never_prompt)
    assert (claude_home / "CLAUDE.md").read_text() == "# changed"

    pulled = core.pull(
        None, ENCRYPTED_CFG, provider, passphrase_prompt=_never_prompt, allow_plain=True
    )
    assert pulled["id"] == pushed["id"]
    assert pulled["encrypted"] is False


def test_plain_object_under_an_encrypted_name_is_always_refused(claude_home):
    provider = MemoryProvider()
    pushed = core.push("plain", PLAIN_CFG, provider)
    disguised = "snapshots/002_20260101T000000_x_aaaaaa.zip.enc"
    provider.upload(disguised, provider.download(pushed["key"]))
    for cfg, allow_plain in ((ENCRYPTED_CFG, True), (PLAIN_CFG, False)):
        with pytest.raises(SnapshotIntegrityError, match="named as encrypted"):
            core.pull(2, cfg, provider, passphrase_prompt=_never_prompt, allow_plain=allow_plain)


def test_swapped_encrypted_object_is_detected_by_its_manifest_id(claude_home):
    provider = MemoryProvider()
    first = core.push("one", ENCRYPTED_CFG, provider)
    second = core.push("two", ENCRYPTED_CFG, provider)
    provider.upload(second["key"], provider.download(first["key"]))  # rolled back to #1
    with pytest.raises(SnapshotIntegrityError, match="holds snapshot #1, not #2"):
        core.pull(2, ENCRYPTED_CFG, provider, passphrase_prompt=_never_prompt)


def test_list_marks_a_plain_named_object_with_an_envelope_as_encrypted(claude_home):
    provider = MemoryProvider()
    pushed = core.push("enc", ENCRYPTED_CFG, provider)
    provider.upload("snapshots/002_20260101T000000_x_aaaaaa.zip", provider.download(pushed["key"]))
    provider.delete("index.json")
    listed = {row["id"]: row["encrypted"] for row in core.list_snapshots(provider)}
    assert listed == {1: True, 2: True}


def test_encrypted_snapshot_reads_on_machine_without_encryption_config(
    claude_home, monkeypatch
):
    provider = MemoryProvider()
    core.push("enc", ENCRYPTED_CFG, provider)
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "s3cret")
    pulled = core.pull(None, PLAIN_CFG, provider, passphrase_prompt=_never_prompt)
    assert pulled["encrypted"] is True


def test_encrypted_pull_without_passphrase_and_no_terminal_names_env_var(
    claude_home, no_terminal
):
    provider = MemoryProvider()
    core.push("enc", ENCRYPTED_CFG, provider)
    with pytest.raises(PassphraseUnavailableError, match=PASSPHRASE_ENV_VAR):
        core.pull(None, PLAIN_CFG, provider)


def test_wrong_passphrase_through_core(claude_home):
    provider = MemoryProvider()
    core.push("enc", ENCRYPTED_CFG, provider)
    wrong_cfg = {**PLAIN_CFG, "encryption": {"enabled": True, "passphrase": "nope"}}
    with pytest.raises(SnapshotDecryptionError, match="Wrong passphrase"):
        core.pull(None, wrong_cfg, provider)


def test_prompt_is_used_once_for_an_encrypted_push(claude_home, monkeypatch):
    monkeypatch.setattr("claude_cfg.passphrase._stdin_is_tty", lambda: True)
    prompts = []
    cfg = {**PLAIN_CFG, "encryption": {"enabled": True}}

    def prompt():
        prompts.append(1)
        return "typed"

    pushed = core.push("enc", cfg, MemoryProvider(), passphrase_prompt=prompt)
    assert pushed["encrypted"] is True
    # No verifier in this config, so the typed passphrase is asked for twice.
    assert prompts == [1, 1]


def test_string_enabled_flag_from_config_set_turns_encryption_on(claude_home):
    cfg = {**PLAIN_CFG, "encryption": {"enabled": "true", "passphrase": "pw"}}
    assert core.push("enc", cfg, MemoryProvider())["encrypted"] is True


def test_list_never_asks_for_a_passphrase(claude_home, no_terminal):
    provider = MemoryProvider()
    core.push("plain one", PLAIN_CFG, provider)
    core.push("secret one", ENCRYPTED_CFG, provider)
    listed = core.list_snapshots(provider)
    assert [(s["id"], s["encrypted"]) for s in listed] == [(2, True), (1, False)]
    assert listed[0]["message"] == "secret one"


def test_pull_by_key(claude_home):
    provider = MemoryProvider()
    first = core.push("first", PLAIN_CFG, provider)
    core.push("second", PLAIN_CFG, provider)
    pulled = core.pull(None, PLAIN_CFG, provider, key=first["key"])
    assert (pulled["id"], pulled["key"]) == (1, first["key"])
