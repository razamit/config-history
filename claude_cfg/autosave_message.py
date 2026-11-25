"""Short descriptions of what changed, for auto-save messages and notices."""

from typing import Sequence

from claude_cfg.display_text import printable_text

AUTO_MESSAGE_PREFIX = "auto: "
FIRST_VERSION_MESSAGE = AUTO_MESSAGE_PREFIX + "first version"
# Snapshot messages and notice lines stay readable on one line.
MESSAGE_LIMIT = 120
FILE_LIST_LIMIT = 80


def count_text(count: int) -> str:
    """``1 file`` or ``3 files``."""
    return f"{count} file" if count == 1 else f"{count} files"


def file_list_text(paths: Sequence[str], limit: int = FILE_LIST_LIMIT) -> str:
    """Paths joined with commas, ending in ``and N more`` once ``limit`` is reached.

    At least one path is always named, cut short when it alone is too long.
    """
    names = [printable_text(path) for path in paths]
    shown: list = []
    for index, name in enumerate(names):
        remaining = len(names) - index - 1
        candidate = ", ".join(shown + [name])
        suffix = f" and {remaining} more" if remaining else ""
        if shown and len(candidate) + len(suffix) > limit:
            return f"{', '.join(shown)} and {len(names) - len(shown)} more"
        shown.append(name if len(name) <= limit else name[: limit - 3] + "...")
    return ", ".join(shown)


def autosave_message(changed_paths: Sequence[str], first_version: bool) -> str:
    """The snapshot message, such as ``auto: 3 files changed (settings.json, ...)``."""
    if first_version:
        return FIRST_VERSION_MESSAGE
    head = f"{AUTO_MESSAGE_PREFIX}{count_text(len(changed_paths))} changed"
    room = MESSAGE_LIMIT - len(head) - len(" ()")
    return f"{head} ({file_list_text(changed_paths, room)})"
