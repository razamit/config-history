"""Pick one snapshot entry out of a listing by id, by key, or as the latest."""

from typing import Optional

from claude_cfg.errors import (
    DuplicateSnapshotIdError,
    NoSnapshotsError,
    SnapshotNotFoundError,
)
from claude_cfg.program_name import command_hint
from claude_cfg.snapshot_index import SnapshotEntry


def select_entry(
    entries: list[SnapshotEntry],
    snapshot_id: Optional[int] = None,
    key: Optional[str] = None,
) -> SnapshotEntry:
    """Return the one entry the caller asked for.

    ``key`` wins when given. Otherwise ``snapshot_id`` picks by id, and with
    neither the highest id is used. If the chosen id belongs to more than one
    object, a :class:`DuplicateSnapshotIdError` lists them so the user can pass
    an exact key instead.
    """
    if not entries:
        raise NoSnapshotsError(f"No snapshots found. Run `{command_hint('push')}` first.")
    if key is not None:
        return _select_by_key(entries, key)
    wanted_id = max(e.snapshot_id for e in entries) if snapshot_id is None else snapshot_id
    matching = [e for e in entries if e.snapshot_id == wanted_id]
    if not matching:
        available = sorted({e.snapshot_id for e in entries})
        raise SnapshotNotFoundError(
            f"Snapshot #{wanted_id} not found. Available: {available}"
        )
    if len(matching) > 1:
        raise DuplicateSnapshotIdError(describe_duplicates(wanted_id, matching))
    return matching[0]


def _select_by_key(entries: list[SnapshotEntry], key: str) -> SnapshotEntry:
    for entry in entries:
        if entry.key == key:
            return entry
    raise SnapshotNotFoundError(
        f"No snapshot with key {key!r}. Run `{command_hint('list')}` to see the keys."
    )


def describe_duplicates(snapshot_id: int, duplicates: list[SnapshotEntry]) -> str:
    lines = [
        f"Snapshot #{snapshot_id} exists more than once, because two machines "
        "pushed at about the same time. Pick one with --key:"
    ]
    for entry in duplicates:
        lines.append(f"  {entry.key}  ({entry.timestamp}, from {entry.machine})")
    return "\n".join(lines)
