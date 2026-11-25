"""Reading and writing snapshot objects on a storage backend.

:class:`SnapshotStore` is the one place that knows how snapshots are named,
encrypted and numbered. Push, pull and list in :mod:`claude_cfg.core` go
through it, and later features (diff, exact restore, status) should too.
"""

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from claude_cfg.encryption import SnapshotCipher, is_encrypted
from claude_cfg.errors import (
    DuplicateSnapshotIdError,
    PassphraseUnavailableError,
    PlainSnapshotRefusedError,
    SnapshotIntegrityError,
    SnapshotRaceError,
)
from claude_cfg.program_name import command_hint
from claude_cfg.providers.base import StorageProvider
from claude_cfg.snapshot import read_manifest
from claude_cfg.snapshot_index import SnapshotEntry, SnapshotIndexManager
from claude_cfg.snapshot_keys import ENCRYPTED_EXTENSION, format_snapshot_key, new_random_suffix
from claude_cfg.snapshot_selection import select_entry

# Builds the zip archive for a given snapshot id. The id is passed in because
# it is written into the archive's manifest, and a push that loses a race with
# another machine has to rebuild its archive under a new id.
ZipBuilder = Callable[[int], bytes]

DEFAULT_MAX_RACE_RETRIES = 5
# A yielding pusher waits up to this long before listing again, so two
# machines that both yielded are unlikely to collide a second time.
RACE_BACKOFF_SECONDS = 1.0
# Removing this push's own object when it yields is tried this many times.
YIELD_DELETE_ATTEMPTS = 3
YIELD_DELETE_RETRY_SECONDS = 0.5


@dataclass(frozen=True)
class StoredSnapshot:
    """The outcome of storing one new snapshot."""

    entry: SnapshotEntry
    file_count: int
    size_bytes: int
    index_updated: bool


@dataclass(frozen=True)
class FetchedSnapshot:
    """A snapshot's plain zip, and whether the stored object was encrypted."""

    zip_bytes: bytes
    encrypted: bool


@dataclass(frozen=True)
class _UploadedObject:
    entry: SnapshotEntry
    file_count: int
    size_bytes: int


class SnapshotStore:
    """Lists, fetches and stores snapshots through an injected provider.

    ``write_cipher`` encrypts new snapshots; leave it None to store them plain.
    ``read_cipher`` opens encrypted snapshots. Whether a stored object is
    encrypted is decided from its bytes. ``refuse_plain`` makes reading a
    plain snapshot an error, for a machine that has encryption turned on.
    ``sleep`` and ``random_source`` pace race retries; tests replace them.
    """

    def __init__(
        self,
        provider: StorageProvider,
        write_cipher: Optional[SnapshotCipher] = None,
        read_cipher: Optional[SnapshotCipher] = None,
        index: Optional[SnapshotIndexManager] = None,
        suffix_factory: Callable[[], str] = new_random_suffix,
        max_race_retries: int = DEFAULT_MAX_RACE_RETRIES,
        refuse_plain: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self._provider = provider
        self._write_cipher = write_cipher
        self._read_cipher = read_cipher
        self._index = index or SnapshotIndexManager(provider)
        self._suffix_factory = suffix_factory
        self._max_race_retries = max_race_retries
        self._refuse_plain = refuse_plain
        self._sleep = sleep
        self._random_source = random_source

    @property
    def encrypts_new_snapshots(self) -> bool:
        return self._write_cipher is not None

    def list_entries(self) -> list[SnapshotEntry]:
        """Every snapshot on the backend, oldest first."""
        return self._index.load_entries()

    def find_entry(
        self, snapshot_id: Optional[int] = None, key: Optional[str] = None
    ) -> SnapshotEntry:
        """One entry by exact key, by id, or the latest when both are None."""
        return select_entry(self.list_entries(), snapshot_id=snapshot_id, key=key)

    def fetch_zip(self, entry: SnapshotEntry) -> bytes:
        """The plain zip archive for ``entry``, decrypted when needed."""
        return self.fetch(entry).zip_bytes

    def fetch(self, entry: SnapshotEntry) -> FetchedSnapshot:
        """Download, check and decrypt one snapshot.

        An object named ``.zip.enc`` must be encrypted, a decrypted manifest
        must carry the id its key names, and a plain object is refused when
        ``refuse_plain`` is set.
        """
        blob = self._provider.download(entry.key)
        if not is_encrypted(blob):
            self._check_plain_allowed(entry)
            return FetchedSnapshot(blob, encrypted=False)
        if self._read_cipher is None:
            raise PassphraseUnavailableError(
                f"Snapshot {entry.key} is encrypted and no passphrase was provided."
            )
        zip_bytes = self._read_cipher.decrypt(blob)
        _check_manifest_id(entry, zip_bytes)
        return FetchedSnapshot(zip_bytes, encrypted=True)

    def _check_plain_allowed(self, entry: SnapshotEntry) -> None:
        if entry.key.endswith(ENCRYPTED_EXTENSION):
            raise SnapshotIntegrityError(
                f"Snapshot {entry.key} is named as encrypted but is not encrypted. "
                "It was not written by claude-cfg; nothing was restored from it."
            )
        if self._refuse_plain:
            raise PlainSnapshotRefusedError(
                f"Snapshot #{entry.snapshot_id} is not encrypted, but encryption is on "
                "for this machine, so it was refused. If it was pushed before encryption "
                "was turned on, run the command again with --allow-plain."
            )

    def delete_snapshots(self, entries: list[SnapshotEntry]) -> None:
        """Delete these snapshot objects, then refresh the metadata cache.

        A cache that cannot be rewritten is not an error: rows for deleted
        objects are ignored on the next listing.
        """
        for entry in entries:
            self._provider.delete(entry.key)
        if entries:
            try:
                self._index.save_cache(self._index.load_entries())
            except Exception:  # noqa: BLE001 - the cache is only a cache
                pass

    def store_zip(self, build_zip: ZipBuilder) -> StoredSnapshot:
        """Store a new snapshot under the next free id.

        After uploading, the snapshot list is read again. If any other object
        has the same id, this push yields: it deletes its own object, waits a
        short random time and tries again under a freshly listed next id. Two
        pushers that see each other both yield, so an id is never kept by
        two objects. This repeats up to ``max_race_retries`` times.
        """
        for attempt in range(self._max_race_retries + 1):
            uploaded = self._upload_new(build_zip, self._next_free_id())
            if not self._has_rival(uploaded.entry):
                return StoredSnapshot(
                    entry=uploaded.entry,
                    file_count=uploaded.file_count,
                    size_bytes=uploaded.size_bytes,
                    index_updated=self._update_cache(uploaded.entry),
                )
            self._withdraw(uploaded.entry)
            if attempt < self._max_race_retries:
                self._sleep(self._random_source() * RACE_BACKOFF_SECONDS)
        raise SnapshotRaceError(
            "Other machines kept pushing at the same moment, so no free snapshot "
            f"id was found after {self._max_race_retries} retries. Push again."
        )

    def _withdraw(self, entry: SnapshotEntry) -> None:
        """Delete this push's own object after yielding, with a few retries.

        If it cannot be deleted, the id now has two objects; say which one is
        left over instead of passing on a raw backend error.
        """
        for attempt in range(YIELD_DELETE_ATTEMPTS):
            try:
                self._provider.delete(entry.key)
                return
            except Exception as error:  # noqa: BLE001 - any backend failure
                failure = error
                if attempt < YIELD_DELETE_ATTEMPTS - 1:
                    self._sleep(YIELD_DELETE_RETRY_SECONDS)
        raise DuplicateSnapshotIdError(
            f"Another machine pushed snapshot #{entry.snapshot_id} at the same moment, and "
            f"this push could not remove its own copy ({type(failure).__name__}). Snapshot "
            f"#{entry.snapshot_id} is now duplicated; the leftover object is {entry.key}. "
            f"Use `{command_hint('pull --key <key>')}` to select one, and delete {entry.key} "
            "from the backend when it can be reached."
        ) from failure

    def _next_free_id(self) -> int:
        ids = [p.snapshot_id for p in self._index.list_parsed_keys()]
        return max(ids) + 1 if ids else 1

    def _upload_new(self, build_zip: ZipBuilder, snapshot_id: int) -> _UploadedObject:
        zip_bytes = build_zip(snapshot_id)
        manifest = read_manifest(zip_bytes)
        encrypted = self._write_cipher is not None
        message = str(manifest.get("message", ""))
        key = format_snapshot_key(
            snapshot_id, manifest["timestamp"], message, self._suffix_factory(), encrypted
        )
        payload = self._write_cipher.encrypt(zip_bytes) if encrypted else zip_bytes
        self._provider.upload(key, payload)
        entry = SnapshotEntry(
            snapshot_id=snapshot_id,
            timestamp=manifest["timestamp"],
            key=key,
            message=message,
            machine=str(manifest.get("machine", "")),
            encrypted=encrypted,
            automatic=manifest.get("automatic") is True,
        )
        return _UploadedObject(entry, len(manifest.get("files", [])), len(payload))

    def _has_rival(self, entry: SnapshotEntry) -> bool:
        """True when another object holds the same id as ``entry``."""
        return any(
            parsed.snapshot_id == entry.snapshot_id and parsed.key != entry.key
            for parsed in self._index.list_parsed_keys()
        )

    def _update_cache(self, new_entry: SnapshotEntry) -> bool:
        """Record the new entry in the metadata cache. Never fails the push."""
        try:
            entries = self._index.load_entries(known_entries=[new_entry])
            self._index.save_cache(entries)
            return True
        except Exception:
            return False


def _check_manifest_id(entry: SnapshotEntry, zip_bytes: bytes) -> None:
    """Refuse a decrypted snapshot whose manifest names another id, which
    means the object was swapped or rolled back on the backend."""
    try:
        manifest_id = read_manifest(zip_bytes).get("id")
    except Exception as error:  # noqa: BLE001 - reported as an integrity failure
        raise SnapshotIntegrityError(
            f"Snapshot {entry.key} decrypted but is not a readable archive ({type(error).__name__})."
        ) from None
    if manifest_id != entry.snapshot_id:
        raise SnapshotIntegrityError(
            f"Snapshot {entry.key} holds snapshot #{manifest_id}, not #{entry.snapshot_id}. "
            "The object may have been swapped or rolled back on the backend; nothing was restored."
        )
