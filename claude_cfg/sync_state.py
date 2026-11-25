"""What this machine last pushed or pulled, kept in ~/.claude-cfg/state.json.

Status compares the current files with ``file_hashes`` here to find local
changes without touching the network, and compares ``snapshot_key`` with the
backend to tell whether another machine has pushed since.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from claude_cfg.content_hashing import content_hash
from claude_cfg.private_file import read_json_or_none, write_private_json
from claude_cfg.snapshot_index import SnapshotEntry

_STATE_FORMAT_VERSION = 1


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SyncState:
    """The snapshot this machine last synced with, and when."""

    snapshot_key: str
    snapshot_id: int
    snapshot_timestamp: str
    machine: str
    content_hash: str
    action: str
    synced_at: str
    file_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"version": _STATE_FORMAT_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, document: object) -> Optional["SyncState"]:
        """A state from its saved form, or None when the document is unusable."""
        if not isinstance(document, dict):
            return None
        try:
            hashes = document.get("file_hashes") or {}
            return cls(
                snapshot_key=str(document["snapshot_key"]),
                snapshot_id=int(document["snapshot_id"]),
                snapshot_timestamp=str(document.get("snapshot_timestamp", "")),
                machine=str(document.get("machine", "")),
                content_hash=str(document.get("content_hash", "")),
                action=str(document.get("action", "")),
                synced_at=str(document.get("synced_at", "")),
                file_hashes={str(k): str(v) for k, v in dict(hashes).items()},
            )
        except (KeyError, TypeError, ValueError):
            return None


class SyncStateStore:
    """Loads and saves :class:`SyncState` at one path."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Optional[SyncState]:
        """The saved state, or None when there is none or it cannot be read."""
        return SyncState.from_dict(read_json_or_none(self._path))

    def save(self, state: SyncState) -> None:
        write_private_json(self._path, state.to_dict())

    def restore(self, saved: Optional[dict]) -> None:
        """Put back a state saved earlier with ``to_dict``; None removes the file."""
        state = SyncState.from_dict(saved)
        if state is None:
            self._path.unlink(missing_ok=True)
        else:
            self.save(state)


def sync_state_for(
    entry: SnapshotEntry, manifest: dict, file_hashes: dict[str, str], action: str
) -> SyncState:
    """The state to record after pushing or pulling ``entry``."""
    return SyncState(
        snapshot_key=entry.key,
        snapshot_id=entry.snapshot_id,
        snapshot_timestamp=entry.timestamp,
        machine=str(manifest.get("machine", entry.machine)),
        content_hash=content_hash(file_hashes),
        action=action,
        synced_at=utc_now_text(),
        file_hashes=dict(file_hashes),
    )
