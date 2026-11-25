"""A check value that tells whether a passphrase is the one set up here.

``init`` and ``config encrypt`` store it in the config as
``encryption.passphrase_verifier``, whether or not the passphrase itself is
saved. A push or a pull on a machine without one stores it once the
passphrase is shown to open the backend's snapshots. It is a salted scrypt hash under its own domain label, so it is never
equal to a key that opens a snapshot and cannot be used to decrypt one. Push
compares a typed or environment passphrase with it, so a typo is caught
before a snapshot is encrypted under the wrong passphrase.
"""

import base64
import binascii
import hmac
import os
from typing import Optional

from claude_cfg.config import VERIFIER_KEY
from claude_cfg.encryption import SCRYPT_LOG2_N, ScryptParameters, derive_key

__all__ = ["VERIFIER_KEY", "create_verifier", "verifier_matches"]
_DOMAIN_LABEL = b"claude-cfg passphrase verifier v1:"
_SALT_BYTES = 16


def create_verifier(passphrase: str) -> dict:
    """A new verifier for ``passphrase`` with a fresh random salt, at the same
    scrypt cost as a snapshot, so it is no cheaper to attack than one."""
    parameters = ScryptParameters(log2_n=SCRYPT_LOG2_N)
    salt = os.urandom(_SALT_BYTES)
    digest = _digest(passphrase, salt, parameters)
    return {
        "version": 1,
        "log2_n": parameters.log2_n,
        "r": parameters.r,
        "p": parameters.p,
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }


def verifier_matches(verifier: object, passphrase: str) -> Optional[bool]:
    """True or False for a usable verifier, None when it is missing or malformed."""
    parsed = _parse(verifier)
    if parsed is None:
        return None
    parameters, salt, expected = parsed
    return hmac.compare_digest(_digest(passphrase, salt, parameters), expected)


def _digest(passphrase: str, salt: bytes, parameters: ScryptParameters) -> bytes:
    return derive_key(passphrase.encode("utf-8"), _DOMAIN_LABEL + salt, parameters)


def _parse(verifier: object) -> Optional[tuple[ScryptParameters, bytes, bytes]]:
    if not isinstance(verifier, dict):
        return None
    try:
        parameters = ScryptParameters(
            log2_n=int(verifier["log2_n"]), r=int(verifier["r"]), p=int(verifier["p"])
        )
        salt = base64.b64decode(verifier["salt"], validate=True)
        expected = base64.b64decode(verifier["hash"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return None
    if not parameters.is_sane() or not salt or not expected:
        return None
    return parameters, salt, expected
