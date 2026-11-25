"""Matching snapshot member names to the names a target folder already holds.

An exact name always wins. Case folding is a fallback used only when the
target folder sits on a case-insensitive filesystem, which
:func:`folder_ignores_case` finds out by writing a probe file there. On a
case-sensitive disk ``Foo.md`` and ``foo.md`` are two files, and both are
restored.

The fallback uses simple case folding plus Unicode NFC, not full casefold,
so ``straße.md`` and ``strasse.md`` stay two names. Trailing dots and spaces
are stripped only on Windows, the one platform that ignores them.

The exclusion filter does not use this module: it folds on every platform
through :func:`claude_cfg.path_identity.path_identity`, because excluding too
much is the safe direction there.
"""

import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable

# Answers whether a folder sits on a case-insensitive filesystem.
CaseProbe = Callable[[Path], bool]

_PROBE_PREFIX = ".claude-cfg-Case-Probe-"


def simple_case_fold(text: str) -> str:
    """Fold each character to one character, the way simple case folding does.

    A character whose full fold is one character uses it; one whose full
    fold grows (``ß`` to ``ss``) is only lowercased, so it stays distinct.
    """
    folded = []
    for character in text:
        full = character.casefold()
        folded.append(full if len(full) == 1 else character.lower())
    return "".join(folded)


class PathMatcher:
    """The comparison key for names in one target folder."""

    def __init__(self, ignores_case: bool, strips_trailing_dots: bool = os.name == "nt") -> None:
        self.ignores_case = ignores_case
        self._strips_trailing_dots = strips_trailing_dots

    def component_key(self, component: str) -> str:
        if component in (".", ".."):
            return component
        if self._strips_trailing_dots:
            component = component.rstrip(". ")
        if self.ignores_case:
            component = simple_case_fold(unicodedata.normalize("NFC", component))
        return component

    def key(self, relative_path: str) -> str:
        """Two posix relative paths name the same file here when their keys match."""
        return "/".join(self.component_key(part) for part in relative_path.split("/"))


def folder_ignores_case(folder: Path) -> bool:
    """True when ``folder`` (or its nearest existing parent) treats names that
    differ only in case as one name.

    Creates a uniquely named file, checks whether its case-swapped name
    exists, and removes it. When nothing can be written there, falls back to
    the platform default: case-insensitive on macOS and Windows.
    """
    existing = folder
    while not existing.is_dir() and existing != existing.parent:
        existing = existing.parent
    try:
        handle, probe_path = tempfile.mkstemp(prefix=_PROBE_PREFIX, dir=existing)
    except OSError:
        return _platform_default()
    try:
        os.close(handle)
        probe = Path(probe_path)
        return (probe.parent / probe.name.swapcase()).exists()
    finally:
        try:
            os.unlink(probe_path)
        except OSError:
            pass


def _platform_default() -> bool:
    return os.name == "nt" or sys.platform == "darwin"


def matcher_for_folder(folder: Path, probe: CaseProbe = folder_ignores_case) -> PathMatcher:
    return PathMatcher(ignores_case=probe(folder))
