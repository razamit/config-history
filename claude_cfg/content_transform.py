"""Converting file bytes between their local form and their stored form.

Stored snapshots hold portable tokens (``${HOME}``, ``${CLAUDE_HOME}``,
``${PYTHON}``) instead of machine paths. :class:`PathTokenTransform` turns
local bytes into stored bytes for one machine, and back again.
"""

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from claude_cfg.paths import (
    CLAUDE_TOKEN,
    HOME_TOKEN,
    PYTHON_TOKEN,
    collapse_interpreter,
    collapse_paths,
    expand_interpreter,
    expand_paths,
    resolve_python,
)


def is_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _transform_json(text: str, transform: Callable[[str], str]) -> tuple[str, bool]:
    """Apply ``transform`` to every string value; reserialize only on change."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        new_text = transform(text)
        return new_text, new_text != text
    new_value, changed = _walk(parsed, transform)
    if not changed:
        return text, False
    return json.dumps(new_value, indent=2), True


def _walk(value, transform: Callable[[str], str]):
    if isinstance(value, dict):
        walked = {key: _walk(item, transform) for key, item in value.items()}
        return {k: v for k, (v, _) in walked.items()}, any(c for _, c in walked.values())
    if isinstance(value, list):
        walked_items = [_walk(item, transform) for item in value]
        return [v for v, _ in walked_items], any(c for _, c in walked_items)
    if isinstance(value, str):
        new_value = transform(value)
        return new_value, new_value != value
    return value, False


def tokenize(
    relative_path: str, content: bytes, home: Path, claude_home: Optional[Path] = None
) -> bytes:
    """Capture-side transform: machine paths become portable tokens.

    Interpreter normalization rides on JSON values only, where command fields
    (hooks, statusLine) live. Paths are collapsed first so script paths are
    already tokenized when :func:`collapse_interpreter` looks for a hint.
    """
    if not is_text(content):
        return content
    text = content.decode("utf-8")
    if relative_path.endswith(".json"):
        new_text, changed = _transform_json(
            text, lambda s: collapse_interpreter(collapse_paths(s, home, claude_home))
        )
    else:
        new_text = collapse_paths(text, home, claude_home)
        changed = new_text != text
    return new_text.encode("utf-8") if changed else content


def detokenize(
    relative_path: str,
    content: bytes,
    home: Path,
    sep: str,
    python: str,
    claude_home: Optional[Path] = None,
) -> bytes:
    """Restore-side transform: portable tokens become native values."""
    if not is_text(content):
        return content
    text = content.decode("utf-8")
    if not any(token in text for token in (HOME_TOKEN, CLAUDE_TOKEN, PYTHON_TOKEN)):
        return content
    if relative_path.endswith(".json"):
        new_text, changed = _transform_json(
            text, lambda s: expand_interpreter(expand_paths(s, home, sep, claude_home), python)
        )
    else:
        new_text = expand_paths(text, home, sep, claude_home)
        changed = new_text != text
    return new_text.encode("utf-8") if changed else content


def native_separator() -> str:
    return "\\" if platform.system() == "Windows" else "/"


@dataclass(frozen=True)
class PathTokenTransform:
    """Token conversion for one machine: its home, Claude folder, separator
    and launcher. ``claude_home`` defaults to ``home/.claude``."""

    home: Path
    sep: str
    python: str
    claude_home: Optional[Path] = None

    @classmethod
    def for_claude_dir(
        cls, claude_dir: Path, home: Optional[Path] = None
    ) -> "PathTokenTransform":
        """The transform for ``claude_dir``. Without ``home`` the folder's
        parent is used, which is right whenever it is ``home/.claude``."""
        return cls(
            home=home if home is not None else claude_dir.parent,
            sep=native_separator(),
            python=resolve_python(),
            claude_home=claude_dir,
        )

    def to_stored(self, relative_path: str, local_content: bytes) -> bytes:
        return tokenize(relative_path, local_content, self.home, self.claude_home)

    def to_local(self, relative_path: str, stored_content: bytes) -> bytes:
        return detokenize(
            relative_path, stored_content, self.home, self.sep, self.python, self.claude_home
        )
