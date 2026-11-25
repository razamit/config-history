"""``restore --only``: restoring some files of a version instead of all.

Each value is a file or a folder inside the snapshot, such as
``settings.json`` or ``skills/demo/``. A value without a trailing ``/``
matches a file of that name or every file under a folder of that name; with
one it matches the folder only. Values pass the same safety rule as tracked
roots (no absolute path, no ``..``), and names match with the restore code's
own rules (:class:`claude_cfg.path_matching.PathMatcher`), so case is folded
only on a disk that ignores case.

Members outside the Claude folder (``_external/``, the MCP server list) are
never part of a partial restore. A partial restore cannot be exact, since
exact removes files the user did not name.
"""

import difflib
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from claude_cfg.errors import RestoreSelectionError
from claude_cfg.external_members import is_external_member
from claude_cfg.path_matching import PathMatcher
from claude_cfg.tracked_files import normalize_root

NEAR_MATCH_COUNT = 5
NEAR_MATCH_CUTOFF = 0.5
EXACT_REFUSED_MESSAGE = (
    "--only restores just the paths you name, and --exact removes files you did not "
    "name, so they cannot be used together. Leave out one of them."
)


def _refuse_option_looking(value: str) -> None:
    """``--only --dry-run`` takes ``--dry-run`` as the path, so the dry run
    would silently become a real restore. A value starting with ``-`` is
    refused; a file whose name starts with ``-`` is named as ``./-name``."""
    if value.strip().startswith("-"):
        raise RestoreSelectionError(
            f"--only needs a path after it, but got {value!r}, which looks like an option. "
            "Nothing was restored. Put a file or folder after each --only, such as "
            "--only settings.json. For a file whose name starts with '-', write ./-name."
        )


def _cleaned_value(value: str) -> str:
    """A value as ``root`` or ``root/``, or an error when it is unsafe."""
    _refuse_option_looking(value)
    root = normalize_root(value)
    if root is None:
        raise RestoreSelectionError(
            f"--only {value!r} is not a path inside the version. Use a relative path "
            "such as settings.json or skills/demo/, without '..' and not starting with '/'."
        )
    is_folder = value.strip().replace("\\", "/").endswith("/")
    return root + "/" if is_folder else root


@dataclass(frozen=True)
class RestoreSelection:
    """The cleaned ``--only`` values, in the order given, without repeats."""

    paths: Tuple[str, ...]

    @classmethod
    def from_values(
        cls, values: Optional[Sequence[str]], exact: bool = False
    ) -> Optional["RestoreSelection"]:
        """None when no ``--only`` was given. Raises before anything is fetched
        when a value is unsafe or ``exact`` is also set."""
        if not values:
            return None
        if exact:
            raise RestoreSelectionError(EXACT_REFUSED_MESSAGE)
        cleaned: List[str] = []
        for value in values:
            path = _cleaned_value(value)
            if path not in cleaned:
                cleaned.append(path)
        return cls(tuple(cleaned))

    def pick(self, member_names: Iterable[str], matcher: PathMatcher) -> Set[str]:
        """The members these paths cover. Raises when a path covers none,
        naming the closest members and folders."""
        names = sorted(name for name in member_names if not is_external_member(name))
        picked: Set[str] = set()
        for path in self.paths:
            found = [name for name in names if covers(path, name, matcher)]
            if not found:
                raise RestoreSelectionError(no_match_message(path, names))
            picked.update(found)
        return picked


def covers(path: str, member_name: str, matcher: PathMatcher) -> bool:
    """Whether the ``--only`` value ``path`` covers the member ``member_name``."""
    folder_key = matcher.key(path.rstrip("/"))
    member_key = matcher.key(member_name)
    if member_key.startswith(folder_key + "/"):
        return True
    return not path.endswith("/") and member_key == folder_key


def folder_names(member_names: Iterable[str]) -> List[str]:
    """Every folder that holds a member, as ``skills/`` and ``skills/demo/``."""
    folders = set()
    for name in member_names:
        parts = name.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            folders.add("/".join(parts[:depth]) + "/")
    return sorted(folders)


def no_match_message(path: str, member_names: Sequence[str]) -> str:
    """The error for a path that covers nothing, with near matches when there are any."""
    candidates = list(member_names) + folder_names(member_names)
    near = difflib.get_close_matches(path, candidates, n=NEAR_MATCH_COUNT, cutoff=NEAR_MATCH_CUTOFF)
    if not near:
        last_part = path.rstrip("/").split("/")[-1].lower()
        near = [name for name in candidates if last_part and last_part in name.lower()]
    message = f"--only {path!r} matches no file or folder in this version, so nothing was restored."
    if near:
        message += " Did you mean: " + ", ".join(near[:NEAR_MATCH_COUNT]) + "?"
    return message
