"""Deciding what a restore would change, without writing anything.

A :class:`RestorePlan` sorts every file into one group. Pull, ``pull
--dry-run`` and ``diff`` all build the same plan, so what is shown is exactly
what a pull then does.

Local files are matched to snapshot members by exact name first. Only when
the target folder ignores case (see :mod:`claude_cfg.path_matching`) does a
file spelled with different case on disk count as the same file, never a
local extra, and keep its on-disk spelling when it is overwritten.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from claude_cfg import path_matching
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.exclusion_filter import is_excluded
from claude_cfg.path_matching import CaseProbe, PathMatcher
from claude_cfg.snapshot_contents import SnapshotContents
from claude_cfg.target_folder import TargetFolderInspector
from claude_cfg.tracked_files import list_tracked_files, safe_roots

CASE_DUPLICATE_REASON = (
    "left untouched, the snapshot has another file whose name differs only in case, "
    "and this folder treats them as one name"
)


@dataclass(frozen=True)
class RestorePlan:
    """What restoring one snapshot onto ``target_dir`` would do.

    ``to_create`` and ``to_overwrite`` are written, ``to_delete`` is removed,
    ``unchanged`` and ``only_local`` (when not exact) are left alone.
    ``content_to_write`` holds the native bytes for every file to write.
    ``left_untouched`` maps a snapshot file that is skipped to the reason,
    such as a symlink that points outside the folder. ``conflicts`` lists
    places where a file and a folder are swapped; a plan with any is refused.
    ``tracked_roots`` are the roots an exact pull may delete inside.
    """

    target_dir: Path
    tracked_roots: list[str]
    exact: bool
    to_create: list[str] = field(default_factory=list)
    to_overwrite: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    only_local: list[str] = field(default_factory=list)
    to_delete: list[str] = field(default_factory=list)
    left_untouched: dict[str, str] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    content_to_write: dict[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def files_to_write(self) -> list[str]:
        return sorted(self.to_create + self.to_overwrite)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_create or self.to_overwrite or self.to_delete)


class RestorePlanner:
    """Compares a snapshot with a folder on disk."""

    def __init__(
        self, transform: PathTokenTransform, case_probe: Optional[CaseProbe] = None
    ) -> None:
        self._transform = transform
        self._case_probe = case_probe or path_matching.folder_ignores_case

    def plan(
        self,
        contents: SnapshotContents,
        target_dir: Path,
        tracked_roots: list[str],
        exact: bool,
    ) -> RestorePlan:
        roots = safe_roots(tracked_roots)
        plan = RestorePlan(target_dir=target_dir, tracked_roots=roots, exact=exact)
        matcher = PathMatcher(ignores_case=self._case_probe(target_dir))
        inspector = TargetFolderInspector(target_dir, matcher)
        members = {
            name: stored
            for name, stored in contents.stored_files.items()
            if not is_excluded(name)
        }
        chosen = self._one_member_per_name(members, matcher, inspector)
        for member_name in sorted(members):
            if member_name not in chosen:
                plan.left_untouched[member_name] = CASE_DUPLICATE_REASON
                continue
            self._classify_snapshot_file(plan, inspector, member_name, members[member_name])
        member_keys = {matcher.key(name) for name in members}
        plan.only_local.extend(self._only_local(member_keys, matcher, target_dir, roots))
        if exact:
            plan.to_delete.extend(plan.only_local)
        return plan

    @staticmethod
    def _one_member_per_name(
        members: dict[str, bytes], matcher: PathMatcher, inspector: TargetFolderInspector
    ) -> set[str]:
        """The members to restore when several map to one name on this disk.

        On a case-sensitive disk every member has its own name. Otherwise the
        member spelled exactly like the file on disk wins, then the first in
        sorted order.
        """
        groups: dict[str, list[str]] = {}
        for name in sorted(members):
            groups.setdefault(matcher.key(name), []).append(name)
        chosen: set[str] = set()
        for names in groups.values():
            exact = [name for name in names if inspector.exists_exactly(name)]
            chosen.add((exact or names)[0])
        return chosen

    def _classify_snapshot_file(
        self, plan: RestorePlan, inspector: TargetFolderInspector, member_name: str, stored: bytes
    ) -> None:
        relative_path = inspector.on_disk_spelling(member_name)
        symlink_target = inspector.outside_symlink(relative_path)
        if symlink_target is not None:
            plan.left_untouched[relative_path] = f"left untouched, it is a symlink to {symlink_target}"
            return
        conflict = inspector.shape_conflict(relative_path)
        if conflict is not None:
            plan.conflicts.append(conflict)
            return
        native = self._transform.to_local(member_name, stored)
        local_path = plan.target_dir / relative_path
        if not local_path.is_file():
            plan.to_create.append(relative_path)
            plan.content_to_write[relative_path] = native
            return
        if self._same_content(member_name, local_path.read_bytes(), native, stored):
            plan.unchanged.append(relative_path)
            return
        plan.to_overwrite.append(relative_path)
        plan.content_to_write[relative_path] = native

    def _same_content(
        self, relative_path: str, local_content: bytes, native: bytes, stored: bytes
    ) -> bool:
        """Equal as written on this machine, or equal once both are tokenized.

        The second check covers a file that only differs by home path or by
        JSON formatting the tokenizer normalizes.
        """
        if local_content == native:
            return True
        return self._transform.to_stored(relative_path, local_content) == stored

    @staticmethod
    def _only_local(
        member_keys: set[str], matcher: PathMatcher, target_dir: Path, roots: list[str]
    ) -> list[str]:
        """Tracked local files the snapshot does not have, never one behind a
        symlink that leaves the folder."""
        base = target_dir.resolve()
        return [
            relative_path
            for relative_path in list_tracked_files(roots, target_dir)
            if matcher.key(relative_path) not in member_keys
            and (target_dir / relative_path).resolve().is_relative_to(base)
        ]
