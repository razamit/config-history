"""Stored UTC timestamps shown as local, relative text.

The zone is built here rather than loaded from the tz database, so the tests
run the same on every platform, Windows included.
"""

from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from claude_cfg.time_display import LocalTimeFormatter, parse_stored_timestamp

PLUS_TWO = timezone(timedelta(hours=2))


class SpringForwardZone(tzinfo):
    """UTC+1 until 2026-03-29 01:00 UTC, then UTC+2, like Central Europe."""

    SWITCH = datetime(2026, 3, 29, 1, 0)

    def utcoffset(self, moment):
        return timedelta(hours=1)  # only used through fromutc below

    def dst(self, moment):
        return timedelta(0)

    def fromutc(self, moment):
        utc_moment = moment.replace(tzinfo=None)
        offset = timedelta(hours=2 if utc_moment >= self.SWITCH else 1)
        return (utc_moment + offset).replace(tzinfo=self)


def formatter_at(now_utc: str, zone: tzinfo = PLUS_TWO) -> LocalTimeFormatter:
    now = parse_stored_timestamp(now_utc)
    return LocalTimeFormatter(clock=lambda: now, zone=zone)


@pytest.mark.parametrize("stored, expected", [
    ("2026-11-25T18:10:40Z", "just now (today 20:10)"),
    ("2026-11-25T18:10:00Z", "1 minute ago (today 20:10)"),
    ("2026-11-25T17:30:00Z", "41 minutes ago (today 19:30)"),
    ("2026-11-25T16:11:00Z", "2 hours ago (today 18:11)"),
    ("2026-11-25T07:30:00Z", "10 hours ago (today 09:30)"),
    ("2026-11-24T07:30:00Z", "yesterday 09:30"),
    ("2026-11-22T12:05:00Z", "3 days ago (Sun 22 Nov 14:05)"),
    ("2026-11-12T12:05:00Z", "13 days ago (Thu 12 Nov 14:05)"),
    ("2026-11-08T12:05:00Z", "8 Nov 2026 14:05"),
    ("2025-12-31T23:00:00Z", "1 Jan 2026 01:00"),
])
def test_recent_and_older_timestamps(stored, expected):
    assert formatter_at("2026-11-25T18:11:00Z").describe(stored) == expected


def test_day_boundary_uses_the_local_calendar_day():
    """At 00:30 local, 23:50 local the evening before is yesterday, though
    only 40 minutes passed; 00:10 local is today."""
    formatter = formatter_at("2026-11-24T22:30:00Z")  # 00:30 on 25 Nov at UTC+2
    assert formatter.describe("2026-11-24T21:50:00Z") == "40 minutes ago (yesterday 23:50)"
    assert formatter.describe("2026-11-24T22:10:00Z") == "20 minutes ago (today 00:10)"
    assert formatter.describe("2026-11-24T19:00:00Z") == "yesterday 21:00"


def test_day_boundary_differs_from_utc():
    """In UTC the two moments are on the same date; locally they are not."""
    formatter = formatter_at("2026-11-25T10:00:00Z", zone=timezone(timedelta(hours=-5)))
    assert formatter.describe("2026-11-25T02:00:00Z") == "yesterday 21:00"


def test_daylight_saving_change():
    """Across the spring change, hours are real elapsed hours and each time
    uses the offset of its own date."""
    formatter = formatter_at("2026-03-29T10:00:00Z", zone=SpringForwardZone())  # 12:00 local
    assert formatter.describe("2026-03-29T00:30:00Z") == "9 hours ago (today 01:30)"
    assert formatter.describe("2026-03-29T01:30:00Z") == "8 hours ago (today 03:30)"
    assert formatter.describe("2026-03-28T22:30:00Z") == "yesterday 23:30"
    assert formatter.describe("2026-03-26T12:00:00Z") == "3 days ago (Thu 26 Mar 13:00)"


def test_future_timestamp_from_a_skewed_clock():
    formatter = formatter_at("2026-11-25T18:11:00Z")
    assert formatter.describe("2026-11-25T18:20:00Z") == "today 20:20"
    assert formatter.describe("2026-12-02T18:20:00Z") == "2 Dec 2026 20:20"


@pytest.mark.parametrize("text", ["", "not a time", "2026-13-45T00:00:00Z"])
def test_unreadable_text_comes_back_unchanged(text):
    assert formatter_at("2026-11-25T18:11:00Z").describe(text) == text


def test_default_zone_is_the_machine_zone():
    now = datetime(2026, 11, 25, 18, 11, tzinfo=timezone.utc)
    text = LocalTimeFormatter(clock=lambda: now).describe("2026-11-25T16:11:00Z")
    local = datetime(2026, 11, 25, 16, 11, tzinfo=timezone.utc).astimezone()
    assert text.startswith("2 hours ago (") or text.startswith("yesterday")
    assert f"{local.hour:02d}:{local.minute:02d}" in text


@pytest.mark.parametrize("stored, zone, expected", [
    ("9999-12-31T23:59:59Z", PLUS_TWO, "31 Dec 9999 23:59 UTC"),
    ("0001-01-01T00:00:00Z", timezone(timedelta(hours=-5)), "1 Jan 1 00:00 UTC"),
])
def test_dates_at_the_edge_of_the_calendar_fall_back_to_utc(stored, zone, expected):
    """One odd key on a shared backend must not make ``list`` fail."""
    assert formatter_at("2026-11-25T10:00:00Z", zone=zone).describe(stored) == expected


def test_edge_dates_that_fit_the_zone_still_show_local_time():
    far_future = formatter_at("2026-11-25T10:00:00Z", zone=timezone(timedelta(hours=-5)))
    assert far_future.describe("9999-12-31T23:59:59Z") == "31 Dec 9999 18:59"
