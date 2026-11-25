"""Reverting the most recent pull from its backup.

When the pull changed MCP servers, the ``claude mcp`` preflight runs before
anything is touched, and a failing preflight refuses the whole undo. With
``files_only`` the files are put back and the MCP part stays pending in the
backup, so a later undo from a normal terminal finishes it.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from claude_cfg.backup_manager import BackupManager, BackupManifest, BackupRecord
from claude_cfg.content_hashing import file_sha256
from claude_cfg.errors import (
    LegacyBackupError,
    McpUndoBlockedError,
    NothingToUndoError,
    UndoConflictError,
    UndoTargetMismatchError,
)
from claude_cfg.mcp_server_sync import McpApplyResult, McpServerSyncManager
from claude_cfg.program_name import (
    ask_claude_phrase,
    ask_claude_text,
    command_hint,
    terminal_command_hint,
    uses_slash_commands,
)
from claude_cfg.restore_writer import SafeDeleter, write_inside
from claude_cfg.sync_state import SyncStateStore


def force_undo_text() -> str:
    """How to undo anyway when files changed after the pull."""
    if uses_slash_commands():
        return ask_claude_text("undo --force", "undo it anyway and replace those edits")
    return f"Run `{command_hint('undo --force')}` to revert them anyway."


def files_only_undo_text() -> str:
    """The two ways on when MCP servers cannot be put back here."""
    terminal = f"Run `{terminal_command_hint('undo')}` from a normal terminal"
    if uses_slash_commands():
        request = "put the files back now and the MCP servers later"
        return f"{terminal}, or {ask_claude_phrase('undo --files-only', request)}."
    return (
        f"{terminal}, or `{command_hint('undo --files-only')}` to put the files back now "
        "and the MCP servers later."
    )


@dataclass
class UndoResult:
    backup_dir: Path
    snapshot_id: int
    snapshot_key: str
    restored: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    overridden_changes: list[str] = field(default_factory=list)
    mcp_result: Optional[McpApplyResult] = None
    state_restored: bool = False
    mcp_left_pending: bool = False
    files_already_undone: bool = False
    # A partial pull (--only) never changed the sync state, so undo leaves it.
    partial: bool = False
    restored_at: Optional[str] = None


class UndoManager:
    """Puts files and sync state back to how they were before a pull."""

    def __init__(
        self,
        backups: BackupManager,
        target_dir: Path,
        state_store: SyncStateStore,
        mcp_manager: Optional[McpServerSyncManager] = None,
    ) -> None:
        self._backups = backups
        self._target_dir = target_dir
        self._state_store = state_store
        self._mcp_manager = mcp_manager

    def undo(self, force: bool = False, files_only: bool = False) -> UndoResult:
        """Revert the newest pull that has something left to undo.

        Raises :class:`UndoConflictError` when a file changed after the pull,
        unless ``force`` is set, :class:`McpUndoBlockedError` when MCP servers
        need putting back and cannot be here, unless ``files_only`` is set,
        and :class:`LegacyBackupError` for a backup made by claude-cfg 0.2.
        """
        record = self._backups.latest_not_undone()
        manifest = self._require_manifest(record)
        self._require_same_target(manifest)
        if manifest.mcp_undo_pending:
            return self._finish_mcp_part(record, manifest, files_only)
        revert_mcp = manifest.has_mcp_changes and not files_only
        if revert_mcp:
            self._require_mcp_ready()
        changed = self.changed_since_pull(manifest)
        if changed and not force:
            raise UndoConflictError(
                "These files changed after the pull, so undo stopped to keep your "
                f"edits. {force_undo_text()}",
                changed,
            )
        result = self._new_result(record, manifest)
        result.overridden_changes = changed
        self._put_back_saved_files(record, manifest, result)
        self._remove_created_files(manifest, result)
        if revert_mcp:
            self._revert_mcp_servers(manifest, result)
        result.state_restored = self._restore_state_if_current(manifest)
        result.mcp_left_pending = manifest.has_mcp_changes and not revert_mcp
        self._backups.mark_undone(record, mcp_reverted=not result.mcp_left_pending)
        return result

    def _finish_mcp_part(
        self, record: BackupRecord, manifest: BackupManifest, files_only: bool
    ) -> UndoResult:
        """Put back the MCP servers of a pull whose files were already put back."""
        if files_only:
            raise NothingToUndoError(
                "The files of the last pull were already put back; only its MCP server "
                f"changes are left. Run `{terminal_command_hint('undo')}` without --files-only from a "
                "normal terminal to put them back."
            )
        self._require_mcp_ready()
        result = self._new_result(record, manifest)
        result.files_already_undone = True
        self._revert_mcp_servers(manifest, result)
        self._backups.mark_mcp_reverted(record)
        return result

    @staticmethod
    def _new_result(record: BackupRecord, manifest: BackupManifest) -> UndoResult:
        return UndoResult(
            record.path,
            manifest.snapshot_id,
            manifest.snapshot_key,
            partial=manifest.partial,
            restored_at=manifest.created_at,
        )

    def _require_mcp_ready(self) -> None:
        problem = (
            self._mcp_manager.preflight_problem()
            if self._mcp_manager is not None
            else "MCP server changes cannot be applied in this context"
        )
        if problem is not None:
            raise McpUndoBlockedError(
                "This pull also changed MCP servers, and they cannot be put back here: "
                f"{problem}. Nothing was changed. {files_only_undo_text()}"
            )

    def _require_same_target(self, manifest: BackupManifest) -> None:
        """Refuse to undo a pull made into another Claude folder, such as one
        a different ``CLAUDE_CONFIG_DIR`` pointed at."""
        current = self._target_dir.resolve()
        if manifest.target_dir is not None and Path(manifest.target_dir) != current:
            raise UndoTargetMismatchError(
                f"The last pull restored into {manifest.target_dir}, but this command "
                f"would undo it in {current}. Set CLAUDE_CONFIG_DIR to match the pull "
                "and run undo again."
            )

    def _restore_state_if_current(self, manifest: BackupManifest) -> bool:
        """Put the earlier sync state back only while the state still points
        at the snapshot this pull restored. A later push or pull moved it on,
        and rewinding past that would hide it. A partial pull never changed
        the state, so there is nothing to put back."""
        if manifest.partial:
            return False
        current = self._state_store.load()
        if current is None or current.snapshot_key != manifest.snapshot_key:
            return False
        self._state_store.restore(manifest.previous_state)
        return True

    def changed_since_pull(self, manifest: BackupManifest) -> list[str]:
        """Files whose current bytes are not what the pull left behind."""
        changed = [
            relative_path
            for relative_path in manifest.created + manifest.overwritten
            if file_sha256(self._target_dir / relative_path)
            != manifest.written_hashes.get(relative_path)
        ]
        changed += [p for p in manifest.deleted if (self._target_dir / p).exists()]
        return sorted(changed)

    @staticmethod
    def _require_manifest(record: BackupRecord) -> BackupManifest:
        if record.manifest is None:
            raise LegacyBackupError(
                "The newest backup was made by claude-cfg 0.2 and has no record of "
                "what the pull changed, so it cannot be undone automatically. Its "
                f"files are in {record.path}; copy back what you need by hand."
            )
        return record.manifest

    def _put_back_saved_files(
        self, record: BackupRecord, manifest: BackupManifest, result: UndoResult
    ) -> None:
        base = self._target_dir.resolve()
        for relative_path in manifest.overwritten + manifest.deleted:
            saved = record.files_dir / relative_path
            if saved.is_file():
                write_inside(self._target_dir, base, relative_path, saved.read_bytes())
                shutil.copymode(saved, self._target_dir / relative_path)
                result.restored.append(relative_path)

    def _revert_mcp_servers(self, manifest: BackupManifest, result: UndoResult) -> None:
        record = manifest.mcp_record
        if record is not None and self._mcp_manager is not None:
            result.mcp_result = self._mcp_manager.revert(record)

    def _remove_created_files(self, manifest: BackupManifest, result: UndoResult) -> None:
        # The created files themselves count as roots here, so a file a pull
        # added outside the recorded roots (older snapshots) can still go.
        deleter = SafeDeleter(self._target_dir, manifest.tracked_roots + manifest.created)
        for relative_path in manifest.created:
            if deleter.delete(relative_path):
                result.removed.append(relative_path)
