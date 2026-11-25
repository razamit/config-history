"""A lock file that only one process can hold at a time.

The lock is a file created with exclusive create, so of two processes that
try at once exactly one succeeds. A lock file older than the stale timeout
is taken to belong to a process that died without removing it, and is
replaced. There is a small window in which two processes can both judge the
same stale file and both take the lock; that needs a crashed holder and two
new processes within the same moment, and the cost is one extra save.
"""

import os
import time
from pathlib import Path
from typing import Callable

from claude_cfg.private_file import PRIVATE_FILE_MODE, make_private_dirs

DEFAULT_STALE_AFTER_SECONDS = 120.0


class ExclusiveFileLock:
    """``try_acquire`` takes the lock or reports that another process has it."""

    def __init__(
        self,
        path: Path,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = path
        self._stale_after_seconds = stale_after_seconds
        self._clock = clock
        self._held = False

    @property
    def path(self) -> Path:
        return self._path

    def try_acquire(self) -> bool:
        """True when this process now holds the lock. Never waits."""
        make_private_dirs(self._path.parent)
        if self._create():
            return True
        if not self._is_stale():
            return False
        self._path.unlink(missing_ok=True)
        return self._create()

    def release(self) -> None:
        if self._held:
            self._path.unlink(missing_ok=True)
            self._held = False

    def _create(self) -> bool:
        try:
            descriptor = os.open(
                self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE_MODE
            )
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        self._held = True
        return True

    def _is_stale(self) -> bool:
        try:
            modified = self._path.stat().st_mtime
        except FileNotFoundError:
            return True
        return self._clock() - modified > self._stale_after_seconds
