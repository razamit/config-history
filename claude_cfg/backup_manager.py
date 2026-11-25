"""Backups taken before a pull, so the pull can be undone.

Each backup is a folder under ~/.claude-cfg/backups named by UTC time. It
holds copies of only the files the pull overwrote or deleted, under
``files/``, and a ``backup-manifest.json`` that says what the pull did. When
the pull changed MCP servers, the manifest also holds their previous
definitions, which often contain tokens, so it is always written owner-only.
Backups made by claude-cfg 0.2 have no manifest; they are listed and pruned
but cannot be undone automatically.

Undo has two parts, the files and the MCP servers. ``undo --files-only``
finishes the first and leaves the second pending; such a backup is offered to
the next undo again and is never pruned, since its manifest is the only copy
of the previous server definitions.
"""

import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from claude_cfg.errors import NothingToUndoError
from claude_cfg.external_members import is_external_member
from claude_cfg.mcp_server_sync import McpBackupRecord
from claude_cfg.private_file import read_json_or_none, write_private_json
from claude_cfg.restore_plan import RestorePlan
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.content_hashing import sha256_hex
from claude_cfg.sync_state import utc_now_text

MANIFEST_NAME = "backup-manifest.json"
PRIVATE_FOLDER_MODE = 0o700
FILES_FOLDER = "files"
DEFAULT_KEEP = 10
_FOLDER_NAME_RE = re.compile(r"^(\d{8}T\d{6}Z)(?:-(\d+))?$")


@dataclass
class BackupManifest:
    """What one pull did, and what it takes to put things back."""

    snapshot_key: str
    snapshot_id: int
    created_at: str
    tracked_roots: list[str]
    overwritten: list[str]
    deleted: list[str]
    created: list[str]
    written_hashes: dict[str, str]
    previous_state: Optional[dict]
    undone_at: Optional[str] = None
    mcp_servers: Optional[dict] = None
    target_dir: Optional[str] = None
    mcp_reverted_at: Optional[str] = None

    @property
    def mcp_record(self) -> Optional[McpBackupRecord]:
        return McpBackupRecord.from_dict(self.mcp_servers)

    @property
    def has_mcp_changes(self) -> bool:
        record = self.mcp_record
        return record is not None and record.has_changes

    @property
    def mcp_undo_pending(self) -> bool:
        """The files were put back but the MCP servers were not yet."""
        return self.undone_at is not None and self.has_mcp_changes and self.mcp_reverted_at is None

    @classmethod
    def from_dict(cls, document: object) -> Optional["BackupManifest"]:
        if not isinstance(document, dict):
            return None
        manifest = cls(**{name: document.get(name) for name in cls.__dataclass_fields__})
        lists_ok = all(
            isinstance(value, list)
            for value in (manifest.tracked_roots, manifest.overwritten, manifest.deleted, manifest.created)
        )
        if not lists_ok or not isinstance(manifest.written_hashes, dict):
            return None
        return manifest


@dataclass(frozen=True)
class BackupRecord:
    """One backup folder. ``manifest`` is None for a 0.2 backup."""

    path: Path
    manifest: Optional[BackupManifest] = field(default=None)

    @property
    def files_dir(self) -> Path:
        return self.path / FILES_FOLDER


def make_private_folder(folder: Path) -> None:
    """Create ``folder`` (and parents) and make it owner-only on POSIX.

    Backups hold copies of config files and MCP definitions, so their folders
    are 0700 whatever the umask is.
    """
    folder.mkdir(parents=True, exist_ok=True, mode=PRIVATE_FOLDER_MODE)
    if os.name != "nt":
        os.chmod(folder, PRIVATE_FOLDER_MODE)


def _folder_sort_key(path: Path) -> tuple[str, int]:
    match = _FOLDER_NAME_RE.match(path.name)
    return (match.group(1), int(match.group(2) or 1)) if match else ("", 0)


class BackupManager:
    """Creates, lists, marks and prunes pull backups in one folder."""

    def __init__(
        self,
        backups_root: Path,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._root = backups_root
        self._clock = clock

    def create(
        self,
        plan: RestorePlan,
        entry: SnapshotEntry,
        previous_state: Optional[dict],
        mcp_record: Optional[McpBackupRecord] = None,
    ) -> Optional[BackupRecord]:
        """Back up what ``plan`` overwrites or deletes, and the MCP servers the
        pull changes. None when nothing changes."""
        mcp_changes = mcp_record is not None and mcp_record.has_changes
        if not plan.has_changes and not mcp_changes:
            return None
        folder = self._new_folder()
        for relative_path in plan.to_overwrite + plan.to_delete:
            if not is_external_member(relative_path):
                self._copy_into(plan.target_dir / relative_path, folder / FILES_FOLDER / relative_path)
        manifest = BackupManifest(
            snapshot_key=entry.key,
            snapshot_id=entry.snapshot_id,
            created_at=utc_now_text(),
            tracked_roots=list(plan.tracked_roots),
            overwritten=list(plan.to_overwrite),
            deleted=list(plan.to_delete),
            created=list(plan.to_create),
            written_hashes={p: sha256_hex(plan.content_to_write[p]) for p in plan.files_to_write},
            previous_state=previous_state,
            mcp_servers=mcp_record.to_dict() if mcp_changes else None,
            target_dir=str(plan.target_dir.resolve()),
        )
        self.save_manifest(BackupRecord(folder, manifest))
        return BackupRecord(folder, manifest)

    def list_backups(self) -> list[BackupRecord]:
        """Every backup folder, newest first."""
        if not self._root.is_dir():
            return []
        folders = [p for p in self._root.iterdir() if p.is_dir() and _FOLDER_NAME_RE.match(p.name)]
        return [
            BackupRecord(folder, BackupManifest.from_dict(read_json_or_none(folder / MANIFEST_NAME)))
            for folder in sorted(folders, key=_folder_sort_key, reverse=True)
        ]

    def latest_not_undone(self) -> BackupRecord:
        """The newest backup with a part still to undo."""
        for record in self.list_backups():
            manifest = record.manifest
            if manifest is None or manifest.undone_at is None or manifest.mcp_undo_pending:
                return record
        raise NothingToUndoError("There is no pull to undo.")

    def mark_undone(self, record: BackupRecord, mcp_reverted: bool = True) -> None:
        """Record that the files were put back, and the MCP servers too unless
        ``mcp_reverted`` is False."""
        if record.manifest is not None:
            record.manifest.undone_at = utc_now_text()
            if mcp_reverted:
                record.manifest.mcp_reverted_at = record.manifest.undone_at
            self.save_manifest(record)

    def mark_mcp_reverted(self, record: BackupRecord) -> None:
        if record.manifest is not None:
            record.manifest.mcp_reverted_at = utc_now_text()
            self.save_manifest(record)

    def save_manifest(self, record: BackupRecord) -> None:
        """Owner-only, since an MCP record holds server definitions."""
        write_private_json(record.path / MANIFEST_NAME, asdict(record.manifest))

    def prune(self, keep: int) -> list[Path]:
        """Delete all but the newest ``keep`` backups, never one whose MCP part
        is still to undo. Returns what was removed."""
        removed = [
            record.path
            for record in self.list_backups()[max(keep, 1):]
            if record.manifest is None or not record.manifest.mcp_undo_pending
        ]
        for folder in removed:
            shutil.rmtree(folder, ignore_errors=True)
        return removed

    def _new_folder(self) -> Path:
        """A folder that sorts after every existing backup from the same second.

        Numbering continues past the highest suffix still on disk, so a name
        freed by pruning is never reused for a newer backup.
        """
        stamp = self._clock().strftime("%Y%m%dT%H%M%SZ")
        same_second = [
            _folder_sort_key(record.path)[1]
            for record in self.list_backups()
            if _folder_sort_key(record.path)[0] == stamp
        ]
        name = f"{stamp}-{max(same_second) + 1}" if same_second else stamp
        folder = self._root / name
        make_private_folder(self._root)
        make_private_folder(folder)
        return folder

    @staticmethod
    def _copy_into(source: Path, destination: Path) -> None:
        """Copy bytes and permission bits, so undo can put both back."""
        destination.parent.mkdir(parents=True, exist_ok=True, mode=PRIVATE_FOLDER_MODE)
        shutil.copy2(source, destination)
