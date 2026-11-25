"""Errors that claude-cfg reports to the user as a plain message.

Every class here derives from :class:`ClaudeCfgError`, so the CLI can print the
message and exit without a traceback. Some also derive from a built-in type
that earlier versions raised, so existing callers that catch those still work.
"""


class ClaudeCfgError(Exception):
    """Base class for expected, user-facing failures."""


class NoSnapshotsError(ClaudeCfgError, RuntimeError):
    """The backend holds no snapshots yet."""


class SnapshotNotFoundError(ClaudeCfgError, ValueError):
    """No snapshot matches the requested id or key."""


class DuplicateSnapshotIdError(ClaudeCfgError):
    """Two snapshot objects share one id, so an id alone is ambiguous."""


class SnapshotRaceError(ClaudeCfgError):
    """A push kept colliding with pushes from other machines."""


class UnsupportedSchemaError(ClaudeCfgError, RuntimeError):
    """A snapshot was written by a newer claude-cfg than this one."""


class SnapshotDecryptionError(ClaudeCfgError):
    """An encrypted snapshot could not be opened."""


class PassphraseUnavailableError(ClaudeCfgError):
    """A passphrase is needed but none was configured or could be asked for."""


class UnsafeSnapshotEntryError(ClaudeCfgError, ValueError):
    """A snapshot names a file outside ~/.claude, so it is refused."""


class ConfirmationRequiredError(ClaudeCfgError):
    """A destructive step needs a yes, and there is no terminal to ask on."""


class NothingToUndoError(ClaudeCfgError):
    """No pull backup is left that has not been undone."""


class LegacyBackupError(ClaudeCfgError):
    """The newest backup was made by claude-cfg 0.2 and has no manifest."""


class UndoConflictError(ClaudeCfgError):
    """Files changed after the pull, so undo would lose those edits."""

    def __init__(self, message: str, changed_files: list[str]) -> None:
        super().__init__(message)
        self.changed_files = changed_files


class McpConfigReadError(ClaudeCfgError):
    """Claude Code's .claude.json or a snapshot's MCP member cannot be read."""


class SettingsFileError(ClaudeCfgError):
    """Claude Code's settings.json cannot be read or has an unexpected shape."""


class RestoreConflictError(ClaudeCfgError):
    """A file sits where the snapshot has a folder, or the reverse."""


class PlainSnapshotRefusedError(ClaudeCfgError):
    """Encryption is on here, and the snapshot to read is not encrypted."""


class SnapshotIntegrityError(ClaudeCfgError):
    """A stored object does not match what its key says it is."""


class McpUndoBlockedError(ClaudeCfgError):
    """Undo would have to change MCP servers, and that cannot be done here."""


class UndoTargetMismatchError(ClaudeCfgError):
    """The pull to undo restored into a different Claude folder than this one."""


class PassphraseMismatchError(ClaudeCfgError):
    """A passphrase does not match the one set up on this machine."""


class BackendLimitError(ClaudeCfgError):
    """The storage backend cannot hold or list what claude-cfg needs."""


class RestoreSelectionError(ClaudeCfgError, ValueError):
    """A ``--only`` path is unsafe, matches nothing, or comes with ``--exact``."""
