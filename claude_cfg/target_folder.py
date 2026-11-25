"""Looking at the folder a restore writes into, before anything is written.

The restore planner asks three questions about each snapshot file: how is it
already spelled on disk, does writing it go through a symlink that leaves the
folder, and does a file sit where a folder should be (or the reverse).
"""

import os
from pathlib import Path
from typing import Optional

from claude_cfg.path_matching import PathMatcher


class TargetFolderInspector:
    """Read-only questions about ``target_dir``. Directory listings are cached."""

    def __init__(self, target_dir: Path, matcher: PathMatcher) -> None:
        self._target_dir = target_dir
        self._base = target_dir.resolve()
        self._matcher = matcher
        self._listings: dict[Path, tuple[set[str], dict[str, str]]] = {}

    def on_disk_spelling(self, relative_path: str) -> str:
        """``relative_path`` with every component that exists on disk spelled
        the way the disk spells it.

        An exact name always wins. Only a folder that ignores case (see
        :class:`PathMatcher`) falls back to a name that matches once folded,
        so writing updates that file instead of creating a case variant.
        """
        current = self._target_dir
        spelled: list[str] = []
        for component in relative_path.split("/"):
            existing = self._existing_name(current, component)
            name = existing if existing is not None else component
            spelled.append(name)
            current = current / name
        return "/".join(spelled)

    def exists_exactly(self, relative_path: str) -> bool:
        """True when every component exists on disk with exactly this spelling."""
        return self.on_disk_spelling(relative_path) == relative_path and (
            self._target_dir / relative_path
        ).exists()

    def _existing_name(self, folder: Path, component: str) -> Optional[str]:
        exact_names, names_by_key = self._listing(folder)
        if component in exact_names:
            return component
        return names_by_key.get(self._matcher.component_key(component))

    def _listing(self, folder: Path) -> tuple[set[str], dict[str, str]]:
        if folder not in self._listings:
            try:
                names = sorted(os.listdir(folder)) if folder.is_dir() else []
            except OSError:
                names = []
            names_by_key: dict[str, str] = {}
            for name in names:
                names_by_key.setdefault(self._matcher.component_key(name), name)
            self._listings[folder] = (set(names), names_by_key)
        return self._listings[folder]

    def outside_symlink(self, relative_path: str) -> Optional[str]:
        """Where a symlink on the way to this file points, when that is
        outside the folder. None when the path stays inside."""
        if (self._target_dir / relative_path).resolve().is_relative_to(self._base):
            return None
        current = self._target_dir
        for component in relative_path.split("/"):
            current = current / component
            if current.is_symlink():
                resolved = current.resolve()
                if not resolved.is_relative_to(self._base):
                    return str(resolved)
        return str((self._target_dir / relative_path).resolve())

    def shape_conflict(self, relative_path: str) -> Optional[str]:
        """Why a file cannot be written here, when a folder or file is in the way."""
        if (self._target_dir / relative_path).is_dir():
            return f"{relative_path} is a folder here but a file in the snapshot"
        parts = relative_path.split("/")
        for depth in range(1, len(parts)):
            prefix = "/".join(parts[:depth])
            candidate = self._target_dir / prefix
            if candidate.exists() and not candidate.is_dir():
                return f"{prefix} is a file here but a folder in the snapshot"
        return None
