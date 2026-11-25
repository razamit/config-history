"""Whether a passphrase opens the snapshots already on a backend.

A passphrase verifier is created from whatever passphrase a machine is first
given. Before one is stored, the newest encrypted snapshot on the backend is
opened with that passphrase, so a typo, or a second machine set up with a
different passphrase, is caught before it writes snapshots that the other
machines cannot read.
"""

from typing import Callable, Optional

from claude_cfg.config import store_passphrase_verifier
from claude_cfg.encryption import PassphraseCipher, SnapshotCipher, is_encrypted
from claude_cfg.errors import PassphraseMismatchError, SnapshotDecryptionError
from claude_cfg.passphrase_verifier import create_verifier
from claude_cfg.providers.base import StorageProvider
from claude_cfg.snapshot_index import SnapshotIndexManager

BACKEND_MISMATCH_MESSAGE = "This passphrase does not open the existing snapshots on this backend."
# A ``.zip.enc`` object without the envelope is skipped; this caps the downloads.
_MAX_OBJECTS_TRIED = 3


class BackendPassphraseCheck:
    """Opens the newest encrypted snapshot on ``provider`` with a passphrase."""

    def __init__(
        self,
        provider: StorageProvider,
        cipher_factory: Callable[[str], SnapshotCipher] = PassphraseCipher,
    ) -> None:
        self._provider = provider
        self._cipher_factory = cipher_factory

    def opens_existing(self, passphrase: str) -> Optional[bool]:
        """True when the passphrase opens the newest encrypted snapshot, False
        when it does not, None when the backend holds no encrypted snapshot.

        Backend errors are raised to the caller.
        """
        parsed_keys = SnapshotIndexManager(self._provider).list_parsed_keys()
        candidates = [parsed for parsed in reversed(parsed_keys) if parsed.encrypted]
        cipher = self._cipher_factory(passphrase)
        for parsed in candidates[:_MAX_OBJECTS_TRIED]:
            blob = self._provider.download(parsed.key)
            if not is_encrypted(blob):
                continue
            try:
                cipher.decrypt(blob)
            except SnapshotDecryptionError:
                return False
            return True
        return None


def confirm_and_record_passphrase(provider: StorageProvider, passphrase: str) -> None:
    """For a push on a machine with no verifier: refuse a passphrase that does
    not open the backend's snapshots, otherwise store its verifier."""
    if BackendPassphraseCheck(provider).opens_existing(passphrase) is False:
        raise PassphraseMismatchError(f"{BACKEND_MISMATCH_MESSAGE} Nothing was pushed.")
    store_passphrase_verifier(create_verifier(passphrase))
