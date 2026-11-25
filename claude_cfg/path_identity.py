"""The broad comparison form of a path, for decisions where folding too much is safe.

macOS and Windows treat ``Skills/Foo.md`` and ``skills/foo.md`` as one file,
macOS stores names in a decomposed Unicode form, and Windows ignores trailing
dots and spaces in each name. The exclusion filter and the tracked-root checks
go through :func:`path_identity` on every platform, so a spelling difference
can never let an excluded name slip through.

Matching snapshot members to files on disk does not use it: that prefers the
exact name and folds only on a case-insensitive disk, see
:mod:`claude_cfg.path_matching`.
"""

import unicodedata


def path_identity(relative_path: str) -> str:
    """The comparison form of a posix relative path.

    Unicode NFC, casefolded, and each component stripped of the trailing dots
    and spaces Windows ignores. Use it only to compare; never write it to disk.
    """
    composed = unicodedata.normalize("NFC", relative_path)
    return "/".join(_component_identity(part) for part in composed.split("/"))


def _component_identity(component: str) -> str:
    if component in (".", ".."):
        return component
    return component.rstrip(". ").casefold()


def same_path(first: str, second: str) -> bool:
    return path_identity(first) == path_identity(second)
