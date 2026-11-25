"""Saving a new version only when the tracked files changed.

:class:`AutoSaveManager` never prompts and never raises: every outcome,
including a failure, comes back as an :class:`AutoSaveResult`. Its
collaborators are injected, so it runs the same against the local history,
a remote backend or a test double. A lock keeps two Claude Code sessions
that start at once from saving the same change twice.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

from claude_cfg.autosave_message import autosave_message
from claude_cfg.display_text import printable_text, shortened
from claude_cfg.errors import PassphraseUnavailableError
from claude_cfg.exclusive_lock import ExclusiveFileLock

REASON_LIMIT = 200


class AutoSaveOutcome(str, Enum):
    SAVED = "saved"
    NO_CHANGES = "no_changes"
    LOCKED = "locked"  # another process is saving right now
    NO_PASSPHRASE = "no_passphrase"  # encryption is on and nothing supplies it
    FAILED = "failed"


@dataclass(frozen=True)
class ChangeReport:
    """What changed since the last saved version.

    ``first_version`` means there is no saved version yet and there are files
    to save. ``error`` is set when the files could not be compared.
    """

    changed_paths: List[str] = field(default_factory=list)
    first_version: bool = False
    error: Optional[str] = None

    @property
    def needs_save(self) -> bool:
        return self.first_version or bool(self.changed_paths)


@dataclass(frozen=True)
class AutoSaveResult:
    outcome: AutoSaveOutcome
    changed_paths: List[str] = field(default_factory=list)
    first_version: bool = False
    snapshot_id: Optional[int] = None
    # The newest version older than the one just saved, to go back to.
    previous_id: Optional[int] = None
    pruned_count: int = 0
    reason: str = ""


@dataclass(frozen=True)
class AutoSaveActions:
    """The work auto-save delegates. Each callable may raise."""

    detect_changes: Callable[[], ChangeReport]
    passphrase_available: Callable[[], bool]
    save_snapshot: Callable[[str], int]  # message -> new snapshot id
    prune_automatic: Callable[[], int]  # -> how many were deleted
    previous_snapshot_id: Callable[[int], Optional[int]]


def error_reason(error: BaseException) -> str:
    """An exception as one short, printable line."""
    text = str(error) or type(error).__name__
    return shortened(printable_text(text), REASON_LIMIT)


class AutoSaveManager:
    """Runs one auto-save: check, save, prune, all under the lock."""

    def __init__(self, actions: AutoSaveActions, lock: ExclusiveFileLock) -> None:
        self._actions = actions
        self._lock = lock

    def run(self) -> AutoSaveResult:
        try:
            if not self._lock.try_acquire():
                return AutoSaveResult(AutoSaveOutcome.LOCKED)
        except Exception as error:  # noqa: BLE001 - reported, never raised
            return AutoSaveResult(AutoSaveOutcome.FAILED, reason=error_reason(error))
        try:
            return self._run_locked()
        except PassphraseUnavailableError as error:
            return AutoSaveResult(AutoSaveOutcome.NO_PASSPHRASE, reason=error_reason(error))
        except Exception as error:  # noqa: BLE001 - reported, never raised
            return AutoSaveResult(AutoSaveOutcome.FAILED, reason=error_reason(error))
        finally:
            self._lock.release()

    def _run_locked(self) -> AutoSaveResult:
        report = self._actions.detect_changes()
        if report.error:
            return AutoSaveResult(AutoSaveOutcome.FAILED, reason=shortened(report.error, REASON_LIMIT))
        if not report.needs_save:
            return AutoSaveResult(AutoSaveOutcome.NO_CHANGES)
        if not self._actions.passphrase_available():
            return AutoSaveResult(
                AutoSaveOutcome.NO_PASSPHRASE, changed_paths=list(report.changed_paths),
                first_version=report.first_version,
            )
        new_id = self._actions.save_snapshot(
            autosave_message(report.changed_paths, report.first_version)
        )
        return AutoSaveResult(
            AutoSaveOutcome.SAVED,
            changed_paths=list(report.changed_paths),
            first_version=report.first_version,
            snapshot_id=new_id,
            pruned_count=self._prune_quietly(),
            previous_id=self._previous_quietly(new_id),
        )

    def _prune_quietly(self) -> int:
        """A failed prune never undoes a save; it is tried again next time."""
        try:
            return self._actions.prune_automatic()
        except Exception:  # noqa: BLE001
            return 0

    def _previous_quietly(self, new_id: int) -> Optional[int]:
        try:
            return self._actions.previous_snapshot_id(new_id)
        except Exception:  # noqa: BLE001
            return None
