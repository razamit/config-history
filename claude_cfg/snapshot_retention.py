"""Deleting the oldest automatic snapshots beyond the number to keep.

Only snapshots made by auto-save are ever candidates. The index cache says
which ones those are, but anyone with write access to a shared backend can
edit that cache, so each candidate's own manifest is read and must say it
is automatic before the snapshot is deleted. A snapshot that cannot be read
or confirmed is kept.
"""

from claude_cfg.snapshot import read_manifest
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.snapshot_store import SnapshotStore


class SnapshotRetentionManager:
    """Prunes automatic snapshots through an injected :class:`SnapshotStore`."""

    def __init__(self, store: SnapshotStore) -> None:
        self._store = store

    def prune_automatic(self, keep: int) -> list[SnapshotEntry]:
        """Delete automatic snapshots older than the newest ``keep`` of them.

        Returns the snapshots that were deleted, oldest first.
        """
        automatic = [entry for entry in self._store.list_entries() if entry.automatic]
        excess = automatic[: max(len(automatic) - max(keep, 1), 0)]
        confirmed = [entry for entry in excess if self._is_confirmed_automatic(entry)]
        self._store.delete_snapshots(confirmed)
        return confirmed

    def _is_confirmed_automatic(self, entry: SnapshotEntry) -> bool:
        try:
            manifest = read_manifest(self._store.fetch_zip(entry))
        except Exception:  # noqa: BLE001 - unreadable means keep it
            return False
        return manifest.get("automatic") is True and manifest.get("id") == entry.snapshot_id
