"""Hashes that identify file contents and whole snapshots."""

import hashlib
from pathlib import Path
from typing import Mapping, Optional


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: Path) -> Optional[str]:
    """The hash of a file on disk, or None when it is missing or unreadable."""
    try:
        return sha256_hex(path.read_bytes())
    except OSError:
        return None


def content_hash(file_hashes: Mapping[str, str]) -> str:
    """One hash over every ``path`` and ``hash`` pair, sorted by path.

    Two snapshots with the same files and the same stored bytes always get the
    same value, whatever order the files were added in.
    """
    digest = hashlib.sha256()
    for relative_path in sorted(file_hashes):
        digest.update(f"{relative_path}\0{file_hashes[relative_path]}\n".encode("utf-8"))
    return digest.hexdigest()
