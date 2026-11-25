"""Whether this machine and the backend have drifted apart.

:func:`compute_sync_status` never raises for a remote problem: a failed
backend lookup is reported in :attr:`RemoteStatus.error`, so it is safe to
call from a hook that must not fail. The remote lookup is skipped entirely
when no lister is passed, and then no network is used at all. The lister is
any callable that returns the backend's entries oldest first, such as
``SnapshotStore(provider).list_entries``.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from claude_cfg import path_matching
from claude_cfg.content_hashing import sha256_hex
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.external_members import is_external_member
from claude_cfg.path_matching import CaseProbe, PathMatcher
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.sync_state import SyncState, SyncStateStore
from claude_cfg.tracked_files import list_tracked_files


RemoteLister = Callable[[], list[SnapshotEntry]]
# Hashes of the ``_external/`` members a push would store right now.
ExternalHasher = Callable[[], dict[str, str]]


class SuggestedAction(str, Enum):
    NONE = "none"
    PUSH = "push"
    PULL = "pull"
    REVIEW = "review"  # both sides changed: look at `diff` before choosing


@dataclass(frozen=True)
class LocalChanges:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.removed)


@dataclass(frozen=True)
class RemoteStatus:
    checked: bool = False
    latest: Optional[SnapshotEntry] = None
    is_newer: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class SyncStatus:
    """Everything ``claude-cfg status`` reports. ``local_changes`` is None
    when there is no sync state to compare with."""

    last_synced: Optional[SyncState]
    local_changes: Optional[LocalChanges]
    remote: RemoteStatus
    suggested_action: SuggestedAction
    local_error: Optional[str] = None


def hash_tracked_files(
    tracked: list[str], claude_dir: Path, transform: PathTokenTransform
) -> dict[str, str]:
    """``{path: sha256}`` of the current files in the form a push would store."""
    hashes: dict[str, str] = {}
    for relative_path in list_tracked_files(tracked, claude_dir):
        try:
            local_content = (claude_dir / relative_path).read_bytes()
        except OSError:
            continue
        hashes[relative_path] = sha256_hex(transform.to_stored(relative_path, local_content))
    return hashes


def compare_hashes(
    recorded: dict[str, str],
    current: dict[str, str],
    disk_ignores_case: Callable[[], bool] = lambda: False,
) -> LocalChanges:
    """Paths are matched by exact name. A recorded path and a current path
    left over on each side are then paired by folded name, but only when
    ``disk_ignores_case`` says the disk treats them as one file."""
    added = {p for p in current if p not in recorded}
    removed = {p for p in recorded if p not in current}
    modified = {p for p in current if p in recorded and recorded[p] != current[p]}
    if added and removed and disk_ignores_case():
        matcher = PathMatcher(ignores_case=True)
        removed_by_key = {matcher.key(p): p for p in sorted(removed)}
        for path in sorted(added):
            old_spelling = removed_by_key.pop(matcher.key(path), None)
            if old_spelling is None:
                continue
            added.discard(path)
            removed.discard(old_spelling)
            if recorded[old_spelling] != current[path]:
                modified.add(path)
    return LocalChanges(added=sorted(added), modified=sorted(modified), removed=sorted(removed))


def check_remote(list_remote_entries: RemoteLister, state: Optional[SyncState]) -> RemoteStatus:
    """The newest snapshot on the backend. Any failure is returned, not raised."""
    try:
        entries = list_remote_entries()
    except Exception as error:  # noqa: BLE001 - reported to the caller instead
        return RemoteStatus(checked=True, error=str(error) or type(error).__name__)
    latest = entries[-1] if entries else None
    if latest is None:
        return RemoteStatus(checked=True)
    if state is None:
        return RemoteStatus(checked=True, latest=latest, is_newer=True)
    is_newer = latest.key != state.snapshot_key and latest.snapshot_id > state.snapshot_id
    return RemoteStatus(checked=True, latest=latest, is_newer=is_newer)


def suggest_action(
    state: Optional[SyncState], local_changes: Optional[LocalChanges], remote: RemoteStatus
) -> SuggestedAction:
    local_changed = local_changes is not None and local_changes.has_changes
    if remote.is_newer:
        return SuggestedAction.REVIEW if local_changed else SuggestedAction.PULL
    if local_changed:
        return SuggestedAction.PUSH
    if state is None and remote.checked and remote.error is None and remote.latest is None:
        return SuggestedAction.PUSH
    return SuggestedAction.NONE


def _local_changes(
    state: SyncState,
    tracked: list[str],
    claude_dir: Path,
    transform: PathTokenTransform,
    external_hashes: Optional[ExternalHasher],
    case_probe: CaseProbe,
) -> LocalChanges:
    """Compare the recorded hashes with the files now on disk.

    Files the last sync recorded are hashed too, even outside the local
    tracked list, so a file is "removed" only when it is gone from disk.
    """
    recorded_files = [p for p in state.file_hashes if not is_external_member(p)]
    current = hash_tracked_files(list(tracked) + recorded_files, claude_dir, transform)
    recorded = dict(state.file_hashes)
    if external_hashes is None:
        recorded = {p: h for p, h in recorded.items() if not is_external_member(p)}
    else:
        current.update(external_hashes())
    return compare_hashes(recorded, current, lambda: case_probe(claude_dir))


def compute_sync_status(
    tracked: list[str],
    claude_dir: Path,
    state_store: SyncStateStore,
    list_remote_entries: Optional[RemoteLister] = None,
    transform: Optional[PathTokenTransform] = None,
    external_hashes: Optional[ExternalHasher] = None,
    case_probe: Optional[CaseProbe] = None,
) -> SyncStatus:
    """Compare local files with the last sync, and the backend when a lister is given.

    Without ``external_hashes`` the ``_external/`` members recorded at the
    last sync are ignored, so turning MCP sync off does not show a change.
    """
    state = state_store.load()
    local_changes, local_error = None, None
    if state is not None:
        try:
            local_changes = _local_changes(
                state,
                tracked,
                claude_dir,
                transform or PathTokenTransform.for_claude_dir(claude_dir),
                external_hashes,
                case_probe or path_matching.folder_ignores_case,
            )
        except Exception as error:  # noqa: BLE001 - a status check must not fail
            local_error = str(error) or type(error).__name__
    remote = (
        check_remote(list_remote_entries, state)
        if list_remote_entries is not None
        else RemoteStatus()
    )
    return SyncStatus(
        last_synced=state,
        local_changes=local_changes,
        remote=remote,
        suggested_action=suggest_action(state, local_changes, remote),
        local_error=local_error,
    )
