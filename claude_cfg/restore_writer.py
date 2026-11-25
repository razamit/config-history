"""Applying a restore plan: write what changed, then delete what it says to.

Every write and delete is checked again here, not only when the plan is
built, so a plan that was tampered with or built from a hostile snapshot
still cannot touch anything outside the tracked roots.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from claude_cfg.errors import RestoreConflictError, UnsafeSnapshotEntryError
from claude_cfg.exclusion_filter import is_excluded
from claude_cfg.external_members import is_external_member
from claude_cfg.restore_plan import RestorePlan
from claude_cfg.snapshot import check_member_name
from claude_cfg.tracked_files import is_root, is_under_roots, normalize_root


@dataclass
class AppliedRestore:
    written: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    refused_deletes: list[str] = field(default_factory=list)


class SafeDeleter:
    """Deletes files under ``target_dir`` only when every safety rule allows it."""

    def __init__(self, target_dir: Path, tracked_roots: list[str]) -> None:
        self._target_dir = target_dir
        self._base = target_dir.resolve()
        self._roots = tracked_roots

    def may_delete(self, relative_path: str) -> bool:
        if normalize_root(relative_path) != relative_path:
            return False
        if is_excluded(relative_path) or not is_under_roots(relative_path, self._roots):
            return False
        path = self._target_dir / relative_path
        if not path.resolve().is_relative_to(self._base):
            return False
        return path.is_file() or path.is_symlink()

    def delete(self, relative_path: str) -> bool:
        """Remove one file and any folders it leaves empty. False when refused."""
        if not self.may_delete(relative_path):
            return False
        (self._target_dir / relative_path).unlink()
        self.remove_empty_folders(relative_path)
        return True

    def remove_empty_folders(self, relative_path: str) -> None:
        """Remove emptied parent folders inside a tracked root, never the root."""
        parent = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
        while parent and not is_root(parent, self._roots) and is_under_roots(parent, self._roots):
            folder = self._target_dir / parent
            if folder.is_symlink() or not folder.is_dir() or any(folder.iterdir()):
                return
            os.rmdir(folder)
            parent = parent.rsplit("/", 1)[0] if "/" in parent else ""


class RestoreWriter:
    """Writes the files a plan changes and deletes the files it removes."""

    @staticmethod
    def check_destinations(plan: RestorePlan) -> None:
        """Refuse the whole plan if a file and a folder are swapped, or if any
        write would land outside the target."""
        if plan.conflicts:
            raise RestoreConflictError(
                "Nothing was written, because a file and a folder are swapped between "
                "this machine and the snapshot. Move these aside and pull again: "
                + "; ".join(plan.conflicts)
            )
        base = plan.target_dir.resolve()
        for relative_path in plan.files_to_write:
            resolve_inside(plan.target_dir, base, relative_path)

    def apply(self, plan: RestorePlan) -> AppliedRestore:
        applied = AppliedRestore()
        base = plan.target_dir.resolve()
        self.check_destinations(plan)
        for relative_path in plan.files_to_write:
            if is_external_member(relative_path):
                continue
            write_inside(plan.target_dir, base, relative_path, plan.content_to_write[relative_path])
            applied.written.append(relative_path)
        deleter = SafeDeleter(plan.target_dir, plan.tracked_roots)
        for relative_path in plan.to_delete:
            if deleter.delete(relative_path):
                applied.deleted.append(relative_path)
            else:
                applied.refused_deletes.append(relative_path)
        return applied


def resolve_inside(target_dir: Path, base: Path, relative_path: str) -> Path:
    """The real destination of a path, refused when it lands outside ``base``."""
    check_member_name(relative_path)
    destination = (target_dir / relative_path).resolve()
    if not destination.is_relative_to(base):
        raise UnsafeSnapshotEntryError(f"Refusing unsafe zip entry: {relative_path!r}")
    return destination


def write_inside(target_dir: Path, base: Path, relative_path: str, content: bytes) -> None:
    """Write one file, refusing any path that resolves outside ``base``."""
    destination = resolve_inside(target_dir, base, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
