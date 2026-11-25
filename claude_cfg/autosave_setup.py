"""Wiring an :class:`AutoSaveManager` to the real change check, push and retention."""

from typing import Callable, Dict, List, Optional

from claude_cfg import core
from claude_cfg.autosave_manager import AutoSaveActions, AutoSaveManager, ChangeReport
from claude_cfg.config import autosave_keep_count
from claude_cfg.exclusive_lock import ExclusiveFileLock
from claude_cfg.passphrase import passphrase_available_without_prompt
from claude_cfg.paths import autosave_lock_file, claude_dir
from claude_cfg.providers import get_provider
from claude_cfg.providers.base import StorageProvider
from claude_cfg.snapshot_retention import SnapshotRetentionManager
from claude_cfg.sync_status import LocalChanges
from claude_cfg.tracked_files import list_tracked_files
from claude_cfg.volatile_paths import without_volatile

ProviderFactory = Callable[[dict], StorageProvider]


def changed_paths(changes: LocalChanges) -> List[str]:
    """Modified files first, then added, then removed, without volatile paths.

    A change to volatile paths alone (see :mod:`claude_cfg.volatile_paths`)
    therefore never asks for a save. They are still captured by the next one.
    """
    every_change = list(changes.modified) + list(changes.added) + list(changes.removed)
    return without_volatile(every_change)


def detect_local_changes(cfg: dict) -> ChangeReport:
    """Compare the tracked files with the last saved version. No network.

    Used by auto-save and by the session notice, never by ``status``, which
    still lists volatile paths.
    """
    sync_status = core.status(cfg)
    if sync_status.local_error:
        return ChangeReport(error=sync_status.local_error)
    if sync_status.last_synced is None:
        has_files = bool(list_tracked_files(core.local_tracked(cfg), claude_dir()))
        return ChangeReport(first_version=has_files)
    changes = sync_status.local_changes
    return ChangeReport(changed_paths=changed_paths(changes) if changes is not None else [])


def build_autosave_manager(
    cfg: dict,
    provider_factory: ProviderFactory = get_provider,
    lock: Optional[ExclusiveFileLock] = None,
) -> AutoSaveManager:
    """An auto-save for ``cfg``. The backend is reached only when a save is due."""
    built: Dict[str, StorageProvider] = {}

    def provider() -> StorageProvider:
        if "provider" not in built:
            built["provider"] = provider_factory(cfg)
        return built["provider"]

    def store():
        return core.build_snapshot_store(cfg, provider(), never_prompt=True)

    def previous_snapshot_id(new_id: int) -> Optional[int]:
        older = [entry.snapshot_id for entry in store().list_entries() if entry.snapshot_id < new_id]
        return max(older) if older else None

    actions = AutoSaveActions(
        detect_changes=lambda: detect_local_changes(cfg),
        passphrase_available=lambda: passphrase_available_without_prompt(cfg),
        save_snapshot=lambda message: core.push(message, cfg, provider(), automatic=True)["id"],
        prune_automatic=lambda: len(
            SnapshotRetentionManager(store()).prune_automatic(autosave_keep_count(cfg))
        ),
        previous_snapshot_id=previous_snapshot_id,
    )
    return AutoSaveManager(actions, lock or ExclusiveFileLock(autosave_lock_file()))
