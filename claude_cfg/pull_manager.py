"""Pulling a snapshot in two steps: plan it with :func:`prepare_pull`, then
apply the plan with :class:`PullManager`.

Splitting the steps lets the CLI show the plan and ask before deleting, and
lets ``pull --dry-run`` and ``diff`` stop after the first step.

A partial pull (``--only``, see :mod:`claude_cfg.restore_selection`) plans
and backs up only the files it covers, never touches MCP servers, and leaves
the sync state alone: the machine does not match the snapshot afterwards,
so the next save records the mix as a new version.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from claude_cfg import snapshot as snap
from claude_cfg.backup_manager import BackupManager, BackupRecord
from claude_cfg.errors import UnsupportedSchemaError
from claude_cfg.mcp_server_plan import McpServerPlan
from claude_cfg.mcp_server_sync import McpApplyResult, McpBackupRecord, McpServerSyncManager
from claude_cfg.restore_plan import RestorePlan, RestorePlanner
from claude_cfg.restore_selection import RestoreSelection
from claude_cfg.restore_writer import AppliedRestore, RestoreWriter
from claude_cfg.snapshot_contents import SnapshotContents
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.snapshot_store import SnapshotStore
from claude_cfg.sync_state import SyncStateStore, sync_state_for
from claude_cfg.tracked_files import shared_roots


@dataclass(frozen=True)
class PreparedPull:
    """A fetched snapshot and the plan for restoring it. Nothing is written yet."""

    entry: SnapshotEntry
    contents: SnapshotContents
    plan: RestorePlan
    mcp_plan: Optional[McpServerPlan] = None
    encrypted: bool = False
    # Set when an encrypted snapshot opened on a machine with no passphrase
    # verifier; applying the pull stores it.
    new_passphrase_verifier: Optional[dict] = field(default=None, repr=False)


# Plans the MCP server part of a pull from the snapshot and the exact flag.
# Returns None when MCP sync is off or the snapshot has no server list.
McpPlanBuilder = Callable[[SnapshotContents, bool], Optional[McpServerPlan]]


@dataclass(frozen=True)
class PullOutcome:
    prepared: PreparedPull
    applied: AppliedRestore
    backup: Optional[BackupRecord]
    pruned: list[Path] = field(default_factory=list)
    mcp_result: Optional[McpApplyResult] = None


def check_schema(entry: SnapshotEntry, manifest: dict) -> None:
    schema = manifest.get("schema_version", 1)
    if schema > snap.SCHEMA_VERSION:
        raise UnsupportedSchemaError(
            f"Snapshot #{entry.snapshot_id} uses schema v{schema}, but this "
            f"claude-cfg only supports up to v{snap.SCHEMA_VERSION}. Upgrade first."
        )


def prepare_pull(
    store: SnapshotStore,
    planner: RestorePlanner,
    target_dir: Path,
    fallback_tracked: list[str],
    snapshot_id: Optional[int] = None,
    key: Optional[str] = None,
    exact: bool = False,
    mcp_planner: Optional[McpPlanBuilder] = None,
    selection: Optional[RestoreSelection] = None,
) -> PreparedPull:
    """Fetch the snapshot and plan the restore. Writes nothing.

    Local extras (and so exact deletes) are looked for only in roots that
    both the snapshot's tracked list and ``fallback_tracked`` (this machine's
    config, expanded the way push expands it) name. Roots only the snapshot
    names are still written to, but never deleted from. Snapshots older than
    schema v4 have no list, so the local one is used for both. With a
    ``selection`` only the members it covers are planned and MCP servers are
    left out.
    """
    entry = store.find_entry(snapshot_id=snapshot_id, key=key)
    fetched = store.fetch(entry)
    check_schema(entry, snap.read_manifest(fetched.zip_bytes))
    contents = SnapshotContents.from_zip(fetched.zip_bytes)
    snapshot_roots = contents.tracked if contents.tracked is not None else fallback_tracked
    roots = shared_roots(snapshot_roots, fallback_tracked)
    plan = planner.plan(contents, target_dir, roots, exact, selection)
    plans_mcp = mcp_planner is not None and selection is None
    mcp_plan = mcp_planner(contents, exact) if plans_mcp else None
    return PreparedPull(
        entry=entry, contents=contents, plan=plan, mcp_plan=mcp_plan, encrypted=fetched.encrypted
    )


class PullManager:
    """Applies a prepared pull with a backup, a state update and pruning."""

    def __init__(
        self,
        backups: BackupManager,
        state_store: SyncStateStore,
        writer: Optional[RestoreWriter] = None,
        mcp_manager: Optional[McpServerSyncManager] = None,
    ) -> None:
        self._backups = backups
        self._state_store = state_store
        self._writer = writer or RestoreWriter()
        self._mcp_manager = mcp_manager

    def apply(self, prepared: PreparedPull, keep_backups: int) -> PullOutcome:
        """Back up, write, delete, apply MCP changes, record the new sync state
        (not after a partial pull) and prune backups.

        Destinations are checked before the backup is taken, so a refused
        pull leaves no backup behind that claims it ran. MCP changes run
        after the files are written, so a missing or failing ``claude``
        command never stops the file restore.
        """
        self._writer.check_destinations(prepared.plan)
        previous = self._state_store.load()
        mcp_record = self._mcp_record_for(prepared)
        backup = self._backups.create(
            prepared.plan, prepared.entry, previous.to_dict() if previous else None, mcp_record
        )
        applied = self._writer.apply(prepared.plan)
        mcp_result = self._apply_mcp(prepared, mcp_record, backup)
        if not prepared.plan.partial:
            self._record_sync_state(prepared)
        pruned = self._backups.prune(keep_backups)
        return PullOutcome(prepared, applied, backup, pruned, mcp_result)

    def _record_sync_state(self, prepared: PreparedPull) -> None:
        self._state_store.save(
            sync_state_for(
                prepared.entry,
                prepared.contents.manifest,
                prepared.contents.file_hashes(),
                action="pull",
            )
        )

    def _mcp_record_for(self, prepared: PreparedPull) -> Optional[McpBackupRecord]:
        mcp_plan = prepared.mcp_plan
        if self._mcp_manager is None or mcp_plan is None or not mcp_plan.has_changes:
            return None
        if prepared.plan.partial:
            return None
        return McpBackupRecord.from_plan(mcp_plan)

    def _apply_mcp(
        self,
        prepared: PreparedPull,
        mcp_record: Optional[McpBackupRecord],
        backup: Optional[BackupRecord],
    ) -> Optional[McpApplyResult]:
        """Run the MCP commands, then keep only what happened in the backup."""
        if mcp_record is None or prepared.mcp_plan is None or self._mcp_manager is None:
            return None
        result = self._mcp_manager.apply(prepared.mcp_plan)
        mcp_record.keep_applied(result)
        if backup is not None and backup.manifest is not None:
            backup.manifest.mcp_servers = mcp_record.to_dict() if mcp_record.has_changes else None
            self._backups.save_manifest(backup)
        return result
