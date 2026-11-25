"""The install lock and the install status for the config-history plugin.

Stdlib only and compatible with Python 3.9. The lock keeps two installs from
running at once. The status file records a failed install, when the next try
is allowed (backing off after each failure) and when the failure was last
reported to the user.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from config_history_state import Clock, read_json_file, remove_file, write_json_file

# The lock goes stale after 30 minutes, longer than the 22 minutes the install
# steps may take together (INSTALL_TIME_BUDGET_SECONDS in
# config_history_installer.py), so a second install never starts mid-build.
STALE_LOCK_SECONDS = 30 * 60
FAILURE_REPORT_INTERVAL_SECONDS = 24 * 60 * 60
# After a failed install the next try waits 1 hour, doubling after each
# further failure up to 24 hours. A new plugin version or root starts over.
RETRY_BASE_SECONDS = 60 * 60
RETRY_MAX_SECONDS = 24 * 60 * 60


def retry_delay(failure_count: int) -> float:
    """Seconds to wait after ``failure_count`` failures in a row."""
    exponent = min(max(failure_count, 1) - 1, 16)
    return min(RETRY_BASE_SECONDS * (2 ** exponent), RETRY_MAX_SECONDS)


class InstallLock:
    """Exclusive lock file so only one install runs at a time."""

    def __init__(self, lock_file: str, clock: Clock, stale_seconds: float = STALE_LOCK_SECONDS):
        self._lock_file = lock_file
        self._clock = clock
        self._stale_seconds = stale_seconds

    def try_acquire(self) -> bool:
        if self._create():
            return True
        if not self.is_stale():
            return False
        remove_file(self._lock_file)
        return self._create()

    def is_held(self) -> bool:
        return os.path.exists(self._lock_file) and not self.is_stale()

    def is_stale(self) -> bool:
        created = self._created_time()
        if created is None:
            return True
        return self._clock() - created >= self._stale_seconds

    def release(self) -> None:
        remove_file(self._lock_file)

    def _create(self) -> bool:
        os.makedirs(os.path.dirname(self._lock_file), mode=0o700, exist_ok=True)
        try:
            descriptor = os.open(self._lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"created": self._clock(), "pid": os.getpid()}, handle)
        return True

    def _created_time(self) -> Optional[float]:
        content = read_json_file(self._lock_file)
        if content and isinstance(content.get("created"), (int, float)):
            return float(content["created"])
        try:
            return os.path.getmtime(self._lock_file)
        except OSError:
            return None


class InstallStatus:
    """Records a failed install, backs off retries and limits how often it is reported."""

    def __init__(self, status_file: str, report_interval: float = FAILURE_REPORT_INTERVAL_SECONDS):
        self._status_file = status_file
        self._report_interval = report_interval

    def _read(self) -> dict:
        return read_json_file(self._status_file) or {}

    def has_failure(self) -> bool:
        return self._read().get("state") == "failed"

    def record_failure(self, reason: str, now: float, target: dict) -> None:
        """Record a failure for ``target`` (plugin version and root) and set the next try."""
        previous = self._read()
        count = previous.get("failure_count") if previous.get("target") == target else 0
        count = (count if isinstance(count, int) else 0) + 1
        content = {
            "state": "failed", "reason": reason, "failed_at": now, "target": target,
            "failure_count": count, "retry_after": now + retry_delay(count),
        }
        if "last_reported" in previous:
            content["last_reported"] = previous["last_reported"]
        write_json_file(self._status_file, content)

    def install_allowed(self, now: float, target: dict) -> bool:
        """False while a failed install of this same target is backing off."""
        content = self._read()
        if content.get("state") != "failed" or content.get("target") != target:
            return True
        retry_after = content.get("retry_after")
        return not isinstance(retry_after, (int, float)) or now >= retry_after

    def should_report(self, now: float) -> bool:
        content = self._read()
        if content.get("state") != "failed":
            return False
        last_reported = content.get("last_reported")
        if not isinstance(last_reported, (int, float)):
            return True
        return now - last_reported >= self._report_interval

    def mark_reported(self, now: float) -> None:
        content = self._read()
        content["last_reported"] = now
        write_json_file(self._status_file, content)

    def clear(self) -> None:
        remove_file(self._status_file)
