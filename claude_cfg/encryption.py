"""Client-side encryption of snapshot archives.

Envelope layout, in order:

    magic       8 bytes   b"CCFGENC2"
    log2(N)     1 byte    scrypt cost, 14 to 18 accepted on read
    r           1 byte    scrypt block size, must be 8
    p           1 byte    scrypt parallelism, must be 1
    salt       16 bytes   random per snapshot, input to scrypt
    nonce      12 bytes   random per snapshot, input to AES-GCM
    ciphertext            AES-256-GCM output, 16-byte tag at the end

The whole header (magic through nonce) is bound as associated data, so
changing any of it breaks the tag. Out-of-range scrypt parameters are refused
before a key is derived, so a hostile object cannot make a reader burn memory:
the most a reader accepts (N=2^18, r=8, p=1) takes about 256 MiB.
Readers detect encryption from the magic bytes alone, never from local config.
"""

import os
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from claude_cfg.errors import SnapshotDecryptionError

ENVELOPE_MAGIC = b"CCFGENC2"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
TAG_BYTES = 16
SCRYPT_LOG2_N = 15
SCRYPT_N = 2**SCRYPT_LOG2_N
SCRYPT_R = 8
SCRYPT_P = 1
MIN_SCRYPT_LOG2_N = 14
MAX_SCRYPT_LOG2_N = 18

_PARAMS_BYTES = 3
_HEADER_BYTES = len(ENVELOPE_MAGIC) + _PARAMS_BYTES + SALT_BYTES + NONCE_BYTES
_DECRYPT_FAILURE = "Wrong passphrase or corrupted snapshot"


class SnapshotCipher(Protocol):
    """Anything that can seal and open a snapshot archive."""

    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, envelope: bytes) -> bytes: ...


def is_encrypted(blob: bytes) -> bool:
    """True when ``blob`` starts with the claude-cfg envelope magic."""
    return blob[: len(ENVELOPE_MAGIC)] == ENVELOPE_MAGIC


@dataclass(frozen=True)
class ScryptParameters:
    log2_n: int = SCRYPT_LOG2_N
    r: int = SCRYPT_R
    p: int = SCRYPT_P

    def to_bytes(self) -> bytes:
        return bytes((self.log2_n, self.r, self.p))

    def is_sane(self, min_log2_n: int = MIN_SCRYPT_LOG2_N) -> bool:
        return (
            min_log2_n <= self.log2_n <= MAX_SCRYPT_LOG2_N
            and self.r == SCRYPT_R
            and self.p == SCRYPT_P
        )


def derive_key(passphrase: bytes, salt: bytes, parameters: ScryptParameters) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=2**parameters.log2_n, r=parameters.r, p=parameters.p)
    return kdf.derive(passphrase)


class PassphraseCipher:
    """scrypt key derivation plus AES-256-GCM, keyed by a passphrase.

    ``scrypt_n`` sets the cost of new envelopes. ``min_log2_n`` is the lowest
    cost a reader accepts; tests lower both to stay fast.
    """

    def __init__(
        self, passphrase: str, scrypt_n: int = SCRYPT_N, min_log2_n: int = MIN_SCRYPT_LOG2_N
    ) -> None:
        if not passphrase:
            raise ValueError("The passphrase must not be empty.")
        self._passphrase = passphrase.encode("utf-8")
        self._parameters = ScryptParameters(log2_n=scrypt_n.bit_length() - 1)
        self._min_log2_n = min(min_log2_n, self._parameters.log2_n)

    def encrypt(self, plaintext: bytes) -> bytes:
        random_part = os.urandom(SALT_BYTES) + os.urandom(NONCE_BYTES)
        header = ENVELOPE_MAGIC + self._parameters.to_bytes() + random_part
        salt, nonce = _salt_and_nonce(header)
        key = derive_key(self._passphrase, salt, self._parameters)
        return header + AESGCM(key).encrypt(nonce, plaintext, header)

    def decrypt(self, envelope: bytes) -> bytes:
        if not is_encrypted(envelope) or len(envelope) < _HEADER_BYTES + TAG_BYTES:
            raise SnapshotDecryptionError(_DECRYPT_FAILURE)
        header = envelope[:_HEADER_BYTES]
        params_start = len(ENVELOPE_MAGIC)
        parameters = ScryptParameters(*header[params_start:params_start + _PARAMS_BYTES])
        if not parameters.is_sane(self._min_log2_n):
            raise SnapshotDecryptionError(
                "Corrupted snapshot: its encryption parameters are outside the allowed range."
            )
        salt, nonce = _salt_and_nonce(header)
        try:
            key = derive_key(self._passphrase, salt, parameters)
            return AESGCM(key).decrypt(nonce, envelope[_HEADER_BYTES:], header)
        except InvalidTag:
            raise SnapshotDecryptionError(_DECRYPT_FAILURE) from None


def _salt_and_nonce(header: bytes) -> tuple[bytes, bytes]:
    salt_start = len(ENVELOPE_MAGIC) + _PARAMS_BYTES
    nonce_start = salt_start + SALT_BYTES
    return header[salt_start:nonce_start], header[nonce_start:nonce_start + NONCE_BYTES]


class DeferredPassphraseCipher:
    """A :class:`PassphraseCipher` that asks for its passphrase on first use.

    Lets a reader hold a cipher without prompting, so a passphrase is only
    requested when an encrypted snapshot is actually opened or written.
    """

    def __init__(
        self,
        passphrase_source: Callable[[], str],
        scrypt_n: int = SCRYPT_N,
        min_log2_n: int = MIN_SCRYPT_LOG2_N,
    ) -> None:
        self._passphrase_source = passphrase_source
        self._scrypt_n = scrypt_n
        self._min_log2_n = min_log2_n
        self._cipher: Optional[PassphraseCipher] = None

    def _resolved(self) -> PassphraseCipher:
        if self._cipher is None:
            self._cipher = PassphraseCipher(
                self._passphrase_source(), scrypt_n=self._scrypt_n, min_log2_n=self._min_log2_n
            )
        return self._cipher

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._resolved().encrypt(plaintext)

    def decrypt(self, envelope: bytes) -> bytes:
        return self._resolved().decrypt(envelope)
