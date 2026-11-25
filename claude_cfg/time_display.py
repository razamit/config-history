"""Showing a stored UTC timestamp the way a person reads a clock.

Timestamps are stored in UTC (``2026-11-25T16:11:00Z``). People see them in
the machine's time zone, with a relative phrase while they are recent:

- ``just now (today 18:11)`` and ``12 minutes ago (today 18:11)``
- ``2 hours ago (today 18:11)``
- ``yesterday 09:30``
- ``3 days ago (Mon 22 Nov 14:05)`` up to :data:`RELATIVE_DAYS_LIMIT` days
- ``8 Nov 2026 14:05`` beyond that

Elapsed time is measured in real seconds, and "today" and "yesterday" are
calendar days in the local zone, so a daylight-saving change never shifts
either. Day and month names are fixed English words, not the locale's.
The clock and the zone are injected, so tests can fix both. A timestamp
whose local time falls outside the calendar is shown in UTC.
"""

from datetime import datetime, timezone, tzinfo
from typing import Callable, Optional

RELATIVE_DAYS_LIMIT = 13
_DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_STORED_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_stored_timestamp(text: str) -> Optional[datetime]:
    """A stored ``...Z`` timestamp as an aware UTC datetime, or None."""
    for stored_format in _STORED_FORMATS:
        try:
            return datetime.strptime(text, stored_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" if count == 1 else f"{count} {unit}s"


class LocalTimeFormatter:
    """Turns stored UTC timestamps into local, relative text.

    ``zone`` None means the machine's own zone, looked up for each instant,
    so an older timestamp gets the offset that applied on its own date.
    """

    def __init__(
        self, clock: Callable[[], datetime] = utc_now, zone: Optional[tzinfo] = None
    ) -> None:
        self._clock = clock
        self._zone = zone

    def describe(self, timestamp: object) -> str:
        """Readable text for a stored timestamp; unreadable input comes back as it is."""
        moment = parse_stored_timestamp(str(timestamp))
        if moment is None:
            return str(timestamp)
        now = self._clock()
        try:
            local, local_now = self._local(moment), self._local(now)
        except (OverflowError, ValueError, OSError):
            # A date at the very edge of the calendar (year 1 or 9999) has no
            # local time on one side of UTC; show it in UTC instead of failing.
            return f"{self._full_date(moment)} UTC"
        seconds = (now - moment).total_seconds()
        days = (local_now.date() - local.date()).days
        if seconds < 0:
            return self._clock_time(local) if days == 0 else self._full_date(local)
        return self._recent_text(seconds, days, local)

    def _recent_text(self, seconds: float, days: int, local: datetime) -> str:
        if seconds < 60:
            return f"just now ({self._day_and_time(days, local)})"
        if seconds < 3600:
            minutes = _plural(int(seconds // 60), "minute")
            return f"{minutes} ago ({self._day_and_time(days, local)})"
        if days == 0:
            return f"{_plural(int(seconds // 3600), 'hour')} ago (today {self._hhmm(local)})"
        if days == 1:
            return f"yesterday {self._hhmm(local)}"
        if days <= RELATIVE_DAYS_LIMIT:
            return f"{_plural(days, 'day')} ago ({self._weekday_date(local)} {self._hhmm(local)})"
        return self._full_date(local)

    def _local(self, moment: datetime) -> datetime:
        return moment.astimezone(self._zone)

    def _day_and_time(self, days: int, local: datetime) -> str:
        return f"{'today' if days == 0 else 'yesterday'} {self._hhmm(local)}"

    def _clock_time(self, local: datetime) -> str:
        return f"today {self._hhmm(local)}"

    @staticmethod
    def _hhmm(local: datetime) -> str:
        return f"{local.hour:02d}:{local.minute:02d}"

    @staticmethod
    def _weekday_date(local: datetime) -> str:
        return f"{_DAY_NAMES[local.weekday()]} {local.day} {_MONTH_NAMES[local.month - 1]}"

    def _full_date(self, local: datetime) -> str:
        return f"{local.day} {_MONTH_NAMES[local.month - 1]} {local.year} {self._hhmm(local)}"
