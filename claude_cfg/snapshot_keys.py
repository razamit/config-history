"""Naming and parsing of snapshot object keys.

Current format::

    snapshots/{id:03d}_{YYYYMMDDTHHMMSS}_{slug}_{6 hex}.zip      (plain)
    snapshots/{id:03d}_{YYYYMMDDTHHMMSS}_{slug}_{6 hex}.zip.enc  (encrypted)

Keys written before 0.3 have no random suffix and are still accepted. Slugs
never contain underscores, dots or slashes, so every part stays unambiguous.
"""

import re
import secrets
from dataclasses import dataclass
from typing import Optional

SNAPSHOT_PREFIX = "snapshots/"
PLAIN_EXTENSION = ".zip"
ENCRYPTED_EXTENSION = ".zip.enc"
DEFAULT_SLUG = "snapshot"
RANDOM_SUFFIX_HEX_CHARS = 6

_KEY_PATTERN = re.compile(
    # A slug holds only letters, digits and hyphens, the characters slugify()
    # produces. Anything else (such as a sync tool's "conflicted copy" name)
    # does not parse and is ignored.
    r"^snapshots/(?P<id>\d+)_(?P<stamp>\d{8}T\d{6})_(?P<slug>(?:[^\W_]|-)*)"
    r"(?:_(?P<suffix>[0-9a-f]{6}))?\.zip(?P<encrypted>\.enc)?$"
)


@dataclass(frozen=True)
class ParsedSnapshotKey:
    """What can be read from a snapshot object key without downloading it."""

    key: str
    snapshot_id: int
    timestamp: str
    slug: str
    encrypted: bool


def slugify(message: str) -> str:
    """Lowercase, hyphen-joined first six words of ``message``."""
    safe = "".join(c if c.isalnum() else "-" for c in message.lower())
    parts = [p for p in safe.split("-") if p]
    return "-".join(parts[:6])


def new_random_suffix() -> str:
    """Six random hex characters that keep concurrent keys distinct."""
    return secrets.token_hex(RANDOM_SUFFIX_HEX_CHARS // 2)


def compact_timestamp(timestamp: str) -> str:
    """``2026-05-06T14:32:00Z`` becomes ``20260506T143200``."""
    return timestamp.replace(":", "").replace("-", "")[:15]


def expand_timestamp(stamp: str) -> str:
    """``20260506T143200`` becomes ``2026-05-06T14:32:00Z``."""
    return (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        f"T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
    )


def format_snapshot_key(
    snapshot_id: int,
    timestamp: str,
    message: str,
    random_suffix: str,
    encrypted: bool,
) -> str:
    slug = slugify(message) or DEFAULT_SLUG
    extension = ENCRYPTED_EXTENSION if encrypted else PLAIN_EXTENSION
    stamp = compact_timestamp(timestamp)
    return f"{SNAPSHOT_PREFIX}{snapshot_id:03d}_{stamp}_{slug}_{random_suffix}{extension}"


def parse_snapshot_key(key: str) -> Optional[ParsedSnapshotKey]:
    """Parse a key in the current or pre-0.3 format; None when it is neither."""
    match = _KEY_PATTERN.match(key)
    if not match:
        return None
    return ParsedSnapshotKey(
        key=key,
        snapshot_id=int(match.group("id")),
        timestamp=expand_timestamp(match.group("stamp")),
        slug=match.group("slug"),
        encrypted=match.group("encrypted") is not None,
    )


def message_from_slug(slug: str) -> str:
    """A readable stand-in message when no cached metadata exists."""
    return slug.replace("-", " ")
