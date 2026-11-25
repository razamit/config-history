"""Keeping a saved tracked list up to date with newer default entries.

The tracked list is saved at ``init``, so an install made before a default
was added never picks it up on its own. These functions find the defaults a
list is missing and merge them in.
"""

from pathlib import Path
from typing import Iterable, Sequence

from claude_cfg.config import DEFAULT_TRACKED
from claude_cfg.tracked_files import normalize_root


def missing_defaults(
    tracked: Iterable[str], defaults: Sequence[str] = DEFAULT_TRACKED
) -> list[str]:
    """Default entries the tracked list does not cover yet, in default order."""
    present = {normalize_root(entry) for entry in tracked}
    return [entry for entry in defaults if normalize_root(entry) not in present]


def merge_missing_defaults(
    tracked: Sequence[str], defaults: Sequence[str] = DEFAULT_TRACKED
) -> tuple[list[str], list[str]]:
    """The tracked list with missing defaults appended, and what was added."""
    added = missing_defaults(tracked, defaults)
    return list(tracked) + added, added


def untracked_defaults_on_disk(
    tracked: Iterable[str], claude_dir: Path, defaults: Sequence[str] = DEFAULT_TRACKED
) -> list[str]:
    """Missing defaults that actually exist in the Claude folder."""
    return [
        entry
        for entry in missing_defaults(tracked, defaults)
        if (claude_dir / entry.rstrip("/")).exists()
    ]
