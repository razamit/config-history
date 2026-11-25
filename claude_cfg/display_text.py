"""Cleaning backend-supplied text before it is shown.

Snapshot messages, machine names and timestamps come from the backend, so
anyone who can write there chooses them. Before display they lose every
character in the Unicode categories Cc (controls such as newlines and
terminal escapes), Cf (format characters such as the bidi override U+202E
and zero-width spaces), Zl and Zp (line and paragraph separators). That keeps
each value on one line and stops it from reordering the text around it.
"""

import unicodedata

HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def printable_text(text: object) -> str:
    """``text`` as a string without control, format or separator characters."""
    return "".join(c for c in str(text) if unicodedata.category(c) not in HIDDEN_CATEGORIES)


def shortened(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, ending in "..." when cut."""
    return text if len(text) <= limit else text[: limit - 3] + "..."
