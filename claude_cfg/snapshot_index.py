"""The snapshot index: which snapshots exist and what we know about them.

The objects under ``snapshots/`` are the source of truth. ``index.json`` is
only a metadata cache (message and machine) keyed by object key. It is kept
in the pre-0.3 ``{"snapshots": [...]}`` list shape, so older claude-cfg
versions can still read a backend that a newer one has written to.
"""

import json
from dataclasses import dataclass
from typing import Iterable, Optional

from claude_cfg.encryption import is_encrypted
from claude_cfg.providers.base import StorageProvider
from claude_cfg.snapshot import read_manifest
from claude_cfg.snapshot_keys import (
    SNAPSHOT_PREFIX,
    ParsedSnapshotKey,
    message_from_slug,
    parse_snapshot_key,
)

INDEX_KEY = "index.json"
UNKNOWN_MACHINE = "unknown"
_CACHE_FORMAT_VERSION = 2


@dataclass(frozen=True)
class SnapshotEntry:
    """One snapshot object on the backend, with its cached metadata."""

    snapshot_id: int
    timestamp: str
    key: str
    message: str
    machine: str
    encrypted: bool
    metadata_known: bool = True
    # Made by auto-save. Only these are ever deleted by retention.
    automatic: bool = False

    def to_dict(self) -> dict:
        """The dict shape the CLI and earlier versions of core returned."""
        return {
            "id": self.snapshot_id,
            "timestamp": self.timestamp,
            "message": self.message,
            "machine": self.machine,
            "key": self.key,
            "encrypted": self.encrypted,
            "automatic": self.automatic,
        }


def sort_entries(entries: Iterable[SnapshotEntry]) -> list[SnapshotEntry]:
    """Oldest first: by id, then by key so ties sort the same everywhere."""
    return sorted(entries, key=lambda e: (e.snapshot_id, e.key))


class SnapshotIndexManager:
    """Builds the snapshot list from object keys and the metadata cache."""

    def __init__(self, provider: StorageProvider) -> None:
        self._provider = provider

    def list_parsed_keys(self) -> list[ParsedSnapshotKey]:
        """Every parseable snapshot key, sorted by id then key."""
        parsed = (parse_snapshot_key(k) for k in self._provider.list_keys(SNAPSHOT_PREFIX))
        return sorted(
            (p for p in parsed if p is not None),
            key=lambda p: (p.snapshot_id, p.key),
        )

    def load_entries(
        self, known_entries: Iterable[SnapshotEntry] = ()
    ) -> list[SnapshotEntry]:
        """All snapshots, oldest first, with cached or repaired metadata.

        ``known_entries`` supplies metadata the caller already has (such as a
        snapshot it just uploaded), which saves downloading it for repair.
        """
        parsed_keys = self.list_parsed_keys()
        cache = self._load_cache(parsed_keys)
        cache.update({entry.key: entry.to_dict() for entry in known_entries})
        entries = [self._entry_for(parsed, cache.get(parsed.key)) for parsed in parsed_keys]
        return sort_entries(entries)

    def save_cache(self, entries: Iterable[SnapshotEntry]) -> None:
        """Write metadata for every entry whose message and machine are known."""
        cached = [
            {
                "id": e.snapshot_id,
                "timestamp": e.timestamp,
                "message": e.message,
                "machine": e.machine,
                "key": e.key,
                "automatic": e.automatic,
            }
            for e in sort_entries(entries)
            if e.metadata_known
        ]
        document = {"version": _CACHE_FORMAT_VERSION, "snapshots": cached}
        self._provider.upload(INDEX_KEY, json.dumps(document, indent=2).encode())

    def _entry_for(
        self, parsed: ParsedSnapshotKey, cached: Optional[dict]
    ) -> SnapshotEntry:
        if cached is not None:
            return SnapshotEntry(
                snapshot_id=parsed.snapshot_id,
                timestamp=parsed.timestamp,
                key=parsed.key,
                message=str(cached.get("message", "")),
                machine=str(cached.get("machine", UNKNOWN_MACHINE)),
                encrypted=parsed.encrypted,
                automatic=cached.get("automatic") is True,
            )
        return self._repair_from_manifest(parsed) or self._slug_entry(parsed, parsed.encrypted)

    @staticmethod
    def _slug_entry(parsed: ParsedSnapshotKey, encrypted: bool) -> SnapshotEntry:
        """An entry with only what the key says, marked as not cached."""
        return SnapshotEntry(
            snapshot_id=parsed.snapshot_id,
            timestamp=parsed.timestamp,
            key=parsed.key,
            message=message_from_slug(parsed.slug),
            machine=UNKNOWN_MACHINE,
            encrypted=encrypted,
            metadata_known=False,
        )

    def _repair_from_manifest(self, parsed: ParsedSnapshotKey) -> Optional[SnapshotEntry]:
        """Best effort: read message and machine from a plain snapshot.

        Encrypted snapshots are skipped so listing never asks for a passphrase,
        and any failure falls back to the slug instead of failing the list.
        An object with a plain name that turns out to be encrypted is listed
        as encrypted, since what was read wins over the name.
        """
        if parsed.encrypted:
            return None
        try:
            blob = self._provider.download(parsed.key)
            if is_encrypted(blob):
                return self._slug_entry(parsed, encrypted=True)
            manifest = read_manifest(blob)
        except Exception:
            return None
        return SnapshotEntry(
            snapshot_id=parsed.snapshot_id,
            timestamp=parsed.timestamp,
            key=parsed.key,
            message=str(manifest.get("message", "")),
            machine=str(manifest.get("machine", UNKNOWN_MACHINE)),
            encrypted=False,
            automatic=manifest.get("automatic") is True,
        )

    def _load_cache(self, parsed_keys: list[ParsedSnapshotKey]) -> dict[str, dict]:
        """Cached metadata keyed by object key; stale and unreadable rows dropped."""
        rows = self._read_cache_rows()
        live_keys = {p.key for p in parsed_keys}
        keys_by_id: dict[int, list[str]] = {}
        for parsed in parsed_keys:
            keys_by_id.setdefault(parsed.snapshot_id, []).append(parsed.key)

        cache: dict[str, dict] = {}
        for row in rows:
            if not _is_well_formed_row(row):
                continue
            key = row.get("key") or _unique_key_for_id(keys_by_id, row.get("id"))
            if key in live_keys:
                cache[key] = row
        return cache

    def _read_cache_rows(self) -> list[dict]:
        try:
            if not self._provider.exists(INDEX_KEY):
                return []
            document = json.loads(self._provider.download(INDEX_KEY))
        except Exception:
            return []
        rows = document.get("snapshots", []) if isinstance(document, dict) else []
        return [row for row in rows if isinstance(row, dict)]


_OPTIONAL_TEXT_FIELDS = ("key", "message", "machine", "timestamp")


def _is_well_formed_row(row: dict) -> bool:
    """A cache row is used only when every field it has is of the right type.

    The cache is written by any machine with backend access, so a row with a
    list for a key or a number for a message is ignored, not trusted.
    """
    if any(name in row and row[name] is not None and not isinstance(row[name], str)
           for name in _OPTIONAL_TEXT_FIELDS):
        return False
    if row.get("automatic") is not None and not isinstance(row["automatic"], bool):
        return False
    snapshot_id = row.get("id")
    return snapshot_id is None or (isinstance(snapshot_id, int) and not isinstance(snapshot_id, bool))


def _unique_key_for_id(keys_by_id: dict[int, list[str]], snapshot_id) -> Optional[str]:
    """Pre-0.3 cache rows may lack ``key``; match them by id when unambiguous."""
    if not isinstance(snapshot_id, int):
        return None
    keys = keys_by_id.get(snapshot_id, [])
    return keys[0] if len(keys) == 1 else None
