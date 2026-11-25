import pytest

from claude_cfg.encryption import (
    ENVELOPE_MAGIC,
    NONCE_BYTES,
    SALT_BYTES,
    TAG_BYTES,
    DeferredPassphraseCipher,
    PassphraseCipher,
    is_encrypted,
)
from claude_cfg.errors import SnapshotDecryptionError

PLAINTEXT = b"PK\x03\x04 pretend this is a zip archive" * 10
HEADER = len(ENVELOPE_MAGIC) + 3 + SALT_BYTES + NONCE_BYTES


def test_round_trip():
    cipher = PassphraseCipher("correct horse")
    envelope = cipher.encrypt(PLAINTEXT)
    assert cipher.decrypt(envelope) == PLAINTEXT


def test_envelope_layout():
    envelope = PassphraseCipher("pw").encrypt(PLAINTEXT)
    assert envelope.startswith(ENVELOPE_MAGIC)
    assert envelope[len(ENVELOPE_MAGIC):len(ENVELOPE_MAGIC) + 3] == bytes((15, 8, 1))
    assert len(envelope) == HEADER + len(PLAINTEXT) + TAG_BYTES
    assert is_encrypted(envelope)
    assert not is_encrypted(PLAINTEXT)


def test_each_encryption_uses_fresh_salt_and_nonce():
    cipher = PassphraseCipher("pw")
    first, second = cipher.encrypt(PLAINTEXT), cipher.encrypt(PLAINTEXT)
    assert first[len(ENVELOPE_MAGIC) + 3:HEADER] != second[len(ENVELOPE_MAGIC) + 3:HEADER]
    assert first != second


def test_a_different_cipher_with_the_same_passphrase_can_decrypt():
    envelope = PassphraseCipher("shared").encrypt(PLAINTEXT)
    assert PassphraseCipher("shared").decrypt(envelope) == PLAINTEXT


def test_wrong_passphrase_raises_clear_error():
    envelope = PassphraseCipher("right").encrypt(PLAINTEXT)
    with pytest.raises(SnapshotDecryptionError, match="Wrong passphrase or corrupted snapshot"):
        PassphraseCipher("wrong").decrypt(envelope)


@pytest.mark.parametrize(
    "position",
    [0, len(ENVELOPE_MAGIC), len(ENVELOPE_MAGIC) + SALT_BYTES, HEADER + 3, -1],
    ids=["magic", "salt", "nonce", "ciphertext", "tag"],
)
def test_any_tampered_byte_is_detected(position):
    cipher = PassphraseCipher("pw")
    envelope = bytearray(cipher.encrypt(PLAINTEXT))
    envelope[position] ^= 0x01
    with pytest.raises(SnapshotDecryptionError):
        cipher.decrypt(bytes(envelope))


def test_truncated_envelope_is_rejected():
    cipher = PassphraseCipher("pw")
    with pytest.raises(SnapshotDecryptionError):
        cipher.decrypt(ENVELOPE_MAGIC + b"short")


def test_empty_passphrase_is_refused():
    with pytest.raises(ValueError):
        PassphraseCipher("")


def test_deferred_cipher_asks_for_the_passphrase_once_and_only_when_used():
    calls = []

    def source():
        calls.append(1)
        return "pw"

    cipher = DeferredPassphraseCipher(source)
    assert calls == []
    envelope = cipher.encrypt(PLAINTEXT)
    assert cipher.decrypt(envelope) == PLAINTEXT
    assert calls == [1]


def test_envelope_magic_names_the_current_layout():
    assert ENVELOPE_MAGIC == b"CCFGENC2"
    assert not is_encrypted(b"CCFGENC1" + bytes(64))


@pytest.mark.parametrize("params", [
    (0, 8, 1), (13, 8, 1), (19, 8, 1), (20, 8, 1), (21, 8, 1), (255, 8, 1),
    (15, 16, 1), (15, 7, 1), (15, 8, 2), (15, 8, 4), (20, 16, 4),
])
def test_out_of_range_scrypt_cost_is_refused_before_deriving_a_key(params, monkeypatch):
    envelope = bytearray(PassphraseCipher("pw").encrypt(PLAINTEXT))
    start = len(ENVELOPE_MAGIC)
    envelope[start:start + 3] = bytes(params)
    monkeypatch.setattr(
        "claude_cfg.encryption.derive_key",
        lambda *args: (_ for _ in ()).throw(AssertionError("derived a key")),
    )
    with pytest.raises(SnapshotDecryptionError, match="outside the allowed range"):
        PassphraseCipher("pw").decrypt(bytes(envelope))


def test_changed_scrypt_parameters_break_the_tag():
    envelope = bytearray(PassphraseCipher("pw").encrypt(PLAINTEXT))
    envelope[len(ENVELOPE_MAGIC)] = 14  # still in range, but bound as associated data
    with pytest.raises(SnapshotDecryptionError, match="Wrong passphrase"):
        PassphraseCipher("pw").decrypt(bytes(envelope))
