"""Thin orchestration for the CLI: wire the managers and run one operation.

The logic lives in the modules named below; this file only builds them from
the config and the paths for this machine.
"""

from dataclasses import replace
from typing import Callable, Optional

from claude_cfg import pull_manager
from claude_cfg import snapshot as snap
from claude_cfg.backend_passphrase_check import confirm_and_record_passphrase
from claude_cfg.backup_manager import BackupManager
from claude_cfg.command_runner import CommandRunner
from claude_cfg.config import (
    VERIFIER_KEY,
    backups_keep_count,
    encryption_settings,
    is_encryption_enabled,
    store_passphrase_verifier,
)
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.encryption import DeferredPassphraseCipher
from claude_cfg.integration_manager import IntegrationManager
from claude_cfg.mcp_sync_setup import (
    build_mcp_manager,
    external_hasher_for_status,
    external_members_for_push,
    mcp_plan_builder,
)
from claude_cfg.passphrase import PassphraseResolver, RememberedPassphrase
from claude_cfg.passphrase_verifier import create_verifier
from claude_cfg.paths import (
    backups_dir,
    claude_dir,
    claude_json_file,
    detect_target,
    home_dir,
    state_file,
)
from claude_cfg.providers.base import StorageProvider
from claude_cfg.pull_manager import PreparedPull, PullManager
from claude_cfg.pull_summary import describe_pull
from claude_cfg.restore_plan import RestorePlanner
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.snapshot_store import SnapshotStore
from claude_cfg.sync_state import SyncStateStore, sync_state_for
from claude_cfg.sync_status import RemoteStatus, SyncStatus, check_remote, compute_sync_status
from claude_cfg.tracked_files import expand_referenced_files
from claude_cfg.undo_manager import UndoManager, UndoResult

# Kept under its old name for callers that imported it from here.
_expand_referenced_files = expand_referenced_files


def build_snapshot_store(
    cfg: dict,
    provider: StorageProvider,
    passphrase_prompt: Optional[Callable[[], str]] = None,
    allow_plain: bool = False,
    repeat_prompt: Optional[Callable[[], str]] = None,
    for_push: bool = False,
    passphrase_source: Optional[Callable[[], str]] = None,
    never_prompt: bool = False,
) -> SnapshotStore:
    """Wire a :class:`SnapshotStore` for this config.

    Reading can always decrypt, asking for the passphrase only when an
    encrypted snapshot is opened. Writing encrypts only when the config turns
    encryption on, and then shares the same cipher so the user is asked once.
    With encryption on, a plain snapshot is refused unless ``allow_plain``.
    ``for_push`` checks the passphrase before it is used: against the
    verifier, or with no verifier, against the backend's newest encrypted
    snapshot. ``passphrase_source`` replaces the usual resolver.
    ``never_prompt`` takes the passphrase only from the environment or the
    config, even when a terminal is attached.
    """
    if passphrase_source is None:
        passphrase_source = PassphraseResolver(
            cfg,
            prompt=passphrase_prompt,
            check_before_push=for_push,
            repeat_prompt=repeat_prompt,
            check_unverified=lambda passphrase: confirm_and_record_passphrase(provider, passphrase),
            stdin_is_tty=(lambda: False) if never_prompt else None,
        ).resolve
    cipher = DeferredPassphraseCipher(passphrase_source)
    encryption_on = is_encryption_enabled(cfg)
    write_cipher = cipher if encryption_on else None
    return SnapshotStore(
        provider,
        write_cipher=write_cipher,
        read_cipher=cipher,
        refuse_plain=encryption_on and not allow_plain,
    )


def this_machine_transform() -> PathTokenTransform:
    """Token conversion for this machine's home and Claude folder, which
    ``CLAUDE_CONFIG_DIR`` may put anywhere."""
    return PathTokenTransform.for_claude_dir(claude_dir(), home_dir())


def local_tracked(cfg: dict) -> list[str]:
    """The config's tracked list plus referenced files, as push expands it."""
    return expand_referenced_files(cfg.get("tracked", []), claude_dir())


def push(
    message: str,
    cfg: dict,
    provider: StorageProvider,
    passphrase_prompt: Optional[Callable[[], str]] = None,
    repeat_prompt: Optional[Callable[[], str]] = None,
    automatic: bool = False,
) -> dict:
    """Store a new snapshot. ``automatic`` marks it as auto-saved and never prompts."""
    source_dir = claude_dir()
    all_tracked = local_tracked(cfg)
    store = build_snapshot_store(
        cfg, provider, passphrase_prompt, repeat_prompt=repeat_prompt, for_push=True,
        never_prompt=automatic,
    )
    external = external_members_for_push(cfg, claude_json_file(), this_machine_transform())
    last_built: dict[str, bytes] = {}

    def build_zip(snapshot_id: int) -> bytes:
        last_built["zip"] = snap.create_zip(
            all_tracked, source_dir, snapshot_id, message, home_dir(), external, automatic
        )
        return last_built["zip"]

    stored = store.store_zip(build_zip)
    manifest = snap.read_manifest(last_built["zip"])
    SyncStateStore(state_file()).save(
        sync_state_for(stored.entry, manifest, manifest["file_hashes"], action="push")
    )
    return {
        "id": stored.entry.snapshot_id,
        "timestamp": stored.entry.timestamp,
        "key": stored.entry.key,
        "file_count": stored.file_count,
        "size_bytes": stored.size_bytes,
        "encrypted": stored.entry.encrypted,
        "index_updated": stored.index_updated,
    }


def prepare_pull(
    snapshot_id: Optional[int],
    cfg: dict,
    provider: StorageProvider,
    key: Optional[str] = None,
    exact: bool = False,
    passphrase_prompt: Optional[Callable[[], str]] = None,
    allow_plain: bool = False,
) -> PreparedPull:
    """Fetch a snapshot and plan its restore. Writes nothing anywhere.

    When an encrypted snapshot opened and the config has no passphrase
    verifier, the prepared pull carries one for :func:`apply_pull` to store.
    """
    transform = this_machine_transform()
    passphrase = RememberedPassphrase(
        PassphraseResolver(cfg, prompt=passphrase_prompt).resolve
    )
    prepared = pull_manager.prepare_pull(
        store=build_snapshot_store(
            cfg, provider, allow_plain=allow_plain, passphrase_source=passphrase
        ),
        planner=RestorePlanner(transform),
        target_dir=claude_dir(),
        fallback_tracked=local_tracked(cfg),
        snapshot_id=snapshot_id,
        key=key,
        exact=exact,
        mcp_planner=mcp_plan_builder(cfg, claude_json_file(), transform),
    )
    if prepared.encrypted and passphrase.value and not encryption_settings(cfg).get(VERIFIER_KEY):
        prepared = replace(prepared, new_passphrase_verifier=create_verifier(passphrase.value))
    return prepared


def apply_pull(
    prepared: PreparedPull, cfg: dict, command_runner: Optional[CommandRunner] = None
) -> dict:
    """Carry out a prepared pull and describe what it did."""
    manager = PullManager(
        BackupManager(backups_dir()),
        SyncStateStore(state_file()),
        mcp_manager=build_mcp_manager(command_runner),
    )
    integration = IntegrationManager.for_claude_dir(claude_dir())
    hook_before = integration.hook_installed()
    outcome = manager.apply(prepared, backups_keep_count(cfg))
    if prepared.new_passphrase_verifier is not None:
        store_passphrase_verifier(prepared.new_passphrase_verifier)
    hook_removed = hook_before and not integration.hook_installed()
    return describe_pull(outcome, detect_target(), session_hook_removed=hook_removed)


def pull(
    snapshot_id: Optional[int],
    cfg: dict,
    provider: StorageProvider,
    key: Optional[str] = None,
    passphrase_prompt: Optional[Callable[[], str]] = None,
    exact: bool = False,
    command_runner: Optional[CommandRunner] = None,
    allow_plain: bool = False,
) -> dict:
    prepared = prepare_pull(
        snapshot_id, cfg, provider, key=key, exact=exact,
        passphrase_prompt=passphrase_prompt, allow_plain=allow_plain,
    )
    return apply_pull(prepared, cfg, command_runner)


def undo(
    force: bool = False,
    command_runner: Optional[CommandRunner] = None,
    files_only: bool = False,
) -> UndoResult:
    """Revert the most recent pull that has not been undone, MCP servers
    included unless ``files_only`` is set."""
    manager = UndoManager(
        BackupManager(backups_dir()),
        claude_dir(),
        SyncStateStore(state_file()),
        mcp_manager=build_mcp_manager(command_runner),
    )
    return manager.undo(force=force, files_only=files_only)


def status(
    cfg: dict, provider_factory: Optional[Callable[[], StorageProvider]] = None
) -> SyncStatus:
    """Local changes since the last sync, plus the backend's latest snapshot
    when ``provider_factory`` is given.

    The provider is built inside the remote check, so a backend that cannot
    even be constructed is reported in the result instead of raised. Listing
    never needs a passphrase, so the store here has no ciphers.
    """
    def list_remote_entries() -> list[SnapshotEntry]:
        return SnapshotStore(provider_factory()).list_entries()

    lister = list_remote_entries if provider_factory is not None else None
    transform = this_machine_transform()
    return compute_sync_status(
        local_tracked(cfg),
        claude_dir(),
        SyncStateStore(state_file()),
        list_remote_entries=lister,
        transform=transform,
        external_hashes=external_hasher_for_status(cfg, claude_json_file(), transform),
    )


def remote_status(provider_factory: Callable[[], StorageProvider]) -> RemoteStatus:
    """Only the backend half of :func:`status`: is there a newer snapshot?

    Skips hashing local files, so it is as quick as one listing. Failures are
    returned in :attr:`RemoteStatus.error`, never raised.
    """
    def list_remote_entries() -> list[SnapshotEntry]:
        return SnapshotStore(provider_factory()).list_entries()

    return check_remote(list_remote_entries, SyncStateStore(state_file()).load())


def list_snapshots(provider: StorageProvider) -> list[dict]:
    """Snapshots newest first. Never asks for a passphrase."""
    store = SnapshotStore(provider)
    return [entry.to_dict() for entry in reversed(store.list_entries())]
