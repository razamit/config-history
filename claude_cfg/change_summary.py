"""The "What changed" text of the plain history list.

Auto-save writes messages such as ``auto: 2 files changed (settings.json,
skills/demo/notes.md)`` (see :mod:`claude_cfg.autosave_message`). The list
shows them as ``settings.json, skills/demo/notes.md changed``. A version
saved by hand shows the user's own message, marked as saved by them.
"""

import re

from claude_cfg.autosave_message import AUTO_MESSAGE_PREFIX, FIRST_VERSION_MESSAGE

FIRST_VERSION_TEXT = "first version"
SAVED_BY_YOU = "saved by you"
_CHANGED_FILES = re.compile(r"^\d+ files? changed \((?P<files>.*)\)$", re.DOTALL)


def automatic_change_text(message: str) -> str:
    """``auto: 2 files changed (a, b)`` as ``a, b changed``; anything else
    without its ``auto:`` prefix."""
    if message == FIRST_VERSION_MESSAGE:
        return FIRST_VERSION_TEXT
    body = message[len(AUTO_MESSAGE_PREFIX):] if message.startswith(AUTO_MESSAGE_PREFIX) else message
    match = _CHANGED_FILES.match(body)
    if match is None:
        return body
    return f"{match.group('files')} changed"


def hand_saved_text(message: str) -> str:
    """The user's message, marked as theirs: ``"before cleanup" (saved by you)``."""
    message = message.strip()
    return f'"{message}" ({SAVED_BY_YOU})' if message else SAVED_BY_YOU


def change_text(message: object, automatic: bool) -> str:
    """What one version changed, in plain words."""
    text = str(message or "")
    return automatic_change_text(text) if automatic else hand_saved_text(text)
