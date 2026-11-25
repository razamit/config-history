"""Tracked files that Claude Code rewrites on its own during a session.

They are still captured and restored, and ``status`` still lists them, but a
change to them alone is not worth a version: it never triggers an automatic
save or a "changes not saved" notice, and they are left out of the file list
in notices and auto-save messages. ``known_marketplaces.json`` is one: its
``lastUpdated`` field changes whenever Claude Code refreshes a marketplace.
"""

from typing import Iterable, List

from claude_cfg.path_identity import path_identity

VOLATILE_PATHS = frozenset({"plugins/known_marketplaces.json"})


def is_volatile(relative_path: str) -> bool:
    """True when ``relative_path`` (posix, relative to the Claude folder) is volatile."""
    return path_identity(relative_path) in VOLATILE_PATHS


def without_volatile(relative_paths: Iterable[str]) -> List[str]:
    """``relative_paths`` in the same order, with volatile paths removed."""
    return [path for path in relative_paths if not is_volatile(path)]
