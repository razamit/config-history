"""The tracked list: which roots under ~/.claude a snapshot covers.

A tracked root is a posix path relative to ~/.claude. A trailing ``/`` marks
a folder, but a root without one is also walked when it is a folder on disk.
Push, restore planning and status all list files through
:func:`list_tracked_files`, so they agree on what "the tracked files" are.
"""

import os
import re
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

from claude_cfg.exclusion_filter import is_excluded, is_excluded_folder
from claude_cfg.path_identity import path_identity
from claude_cfg.paths import CLAUDE_TOKEN


_SEPARATORS = r"[/\\]+"


def _any_separator_pattern(path_text: str) -> str:
    """``path_text`` as a regex that accepts any run of / or \\ between parts.

    The file is read as raw text, so a JSON file spells a Windows path with
    doubled backslashes (``C:\\\\Users\\\\me``); this matches that spelling,
    the native one and the forward-slash one alike.
    """
    return _SEPARATORS.join(re.escape(part) for part in re.split(_SEPARATORS, path_text))


def _reference_pattern(claude_dir: Path) -> re.Pattern:
    """Match references to files under .claude by any spelling a config may use:
    the ~/.claude shortcut, the ${CLAUDE_HOME} token, or an absolute path."""
    bases = [
        _any_separator_pattern(str(claude_dir)),
        _any_separator_pattern("~/.claude"),
        re.escape(CLAUDE_TOKEN),
    ]
    return re.compile(r"(?:" + "|".join(bases) + r")" + _SEPARATORS + r"([\w./\\-]+)", re.IGNORECASE)


def _relative_reference(captured: str) -> str:
    """The captured tail as a posix path, with doubled separators collapsed."""
    return re.sub(_SEPARATORS, "/", captured)


def expand_referenced_files(tracked: list[str], claude_dir: Path) -> list[str]:
    """The tracked list plus every .claude file a tracked file refers to.

    Covers ~/.claude, ${CLAUDE_HOME} and absolute paths, so externalized hook
    or status-line scripts travel with the snapshot however they are spelled.
    """
    referenced: set[str] = set()
    for entry in tracked:
        path = claude_dir / entry.rstrip("/")
        if path.is_file():
            referenced.update(_references_in(path, claude_dir))
    seen = set(tracked)
    return tracked + [ref for ref in sorted(referenced) if ref not in seen]


def _references_in(path: Path, claude_dir: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    base = claude_dir.resolve()
    found: set[str] = set()
    for match in _reference_pattern(claude_dir).finditer(text):
        referenced_path = (claude_dir / _relative_reference(match.group(1))).resolve()
        try:
            safe_relative = referenced_path.relative_to(base)
        except ValueError:
            continue
        if referenced_path.is_file():
            found.add(safe_relative.as_posix())
    return found


def normalize_root(entry: str) -> Optional[str]:
    """A tracked entry as a clean relative posix path, or None when unsafe.

    Absolute paths, ``..`` segments and the whole .claude folder itself are
    refused, so a tracked list read from a snapshot can never point a restore
    or a delete outside ~/.claude.
    """
    cleaned = entry.replace("\\", "/").strip().rstrip("/")
    if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        return None
    parts = [part for part in PurePosixPath(cleaned).parts if part != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def safe_roots(tracked: Iterable[str]) -> list[str]:
    """Normalized tracked roots with unsafe entries and duplicates dropped.

    Two spellings of one root (``Skills`` and ``skills/``) count as one.
    """
    roots: list[str] = []
    seen: set[str] = set()
    for entry in tracked:
        root = normalize_root(entry)
        if root is not None and path_identity(root) not in seen:
            seen.add(path_identity(root))
            roots.append(root)
    return roots


def shared_roots(snapshot_roots: Iterable[str], local_roots: Iterable[str]) -> list[str]:
    """The snapshot's roots that this machine also tracks.

    An exact pull only deletes inside these, so a snapshot cannot widen what
    gets deleted by listing extra roots of its own.
    """
    local_identities = {path_identity(root) for root in safe_roots(local_roots)}
    return [root for root in safe_roots(snapshot_roots) if path_identity(root) in local_identities]


def is_under_roots(relative_path: str, roots: Iterable[str]) -> bool:
    identity = path_identity(relative_path)
    return any(
        identity == root_identity or identity.startswith(root_identity + "/")
        for root_identity in (path_identity(root) for root in roots)
    )


def is_root(relative_path: str, roots: Iterable[str]) -> bool:
    identity = path_identity(relative_path)
    return any(identity == path_identity(root) for root in roots)


def list_tracked_files(tracked: Iterable[str], claude_dir: Path) -> list[str]:
    """Every file under the tracked roots that passes the exclusion filter.

    Sorted, posix, relative to ``claude_dir``. Symlinked folders inside a root
    are not descended into, the same as the walk push has always done.
    """
    found: set[str] = set()
    for root in safe_roots(tracked):
        root_path = claude_dir / root
        if root_path.is_dir():
            found.update(_walk_folder(root_path, claude_dir))
        elif root_path.is_file():
            found.add(root)
    return sorted(relative for relative in found if not is_excluded(relative))


def _walk_folder(folder: Path, claude_dir: Path) -> set[str]:
    files: set[str] = set()
    for current, folders, names in os.walk(folder, followlinks=False):
        current_path = Path(current)
        folders[:] = [
            name
            for name in folders
            if not is_excluded_folder((current_path / name).relative_to(claude_dir).as_posix())
        ]
        for name in names:
            candidate = current_path / name
            if candidate.is_file():
                files.add(candidate.relative_to(claude_dir).as_posix())
    return files
