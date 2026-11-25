"""Writing small files and folders that only the owner can read."""

import json
import os
import secrets
from pathlib import Path

PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700


def make_private_dirs(path: Path) -> None:
    """Create ``path`` and any missing parents, each new one owner-only (0700).

    Folders that already exist keep their mode. Windows ignores the mode; its
    ACLs already default to per-user.
    """
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for folder in reversed(missing):
        try:
            folder.mkdir(mode=PRIVATE_DIR_MODE)
        except FileExistsError:
            continue
        os.chmod(folder, PRIVATE_DIR_MODE)


def write_private_bytes(path: Path, content: bytes) -> None:
    """Write ``content`` owner-only (0600) from the start, then move it into
    place in one step.

    The file is created with ``os.open`` and mode 0600, so it is never
    readable by others, not even for the moment between create and chmod.
    Missing parent folders are created owner-only (0700).
    """
    make_private_dirs(path.parent)
    # A name of its own, so two processes writing the same file never collide.
    partial_path = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.partial")
    descriptor = os.open(partial_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE_MODE)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(partial_path, path)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise


def write_private_json(path: Path, document: object) -> None:
    """Write ``document`` as JSON with :func:`write_private_bytes`."""
    write_private_bytes(path, json.dumps(document, indent=2).encode("utf-8"))


def read_json_or_none(path: Path) -> object:
    """The parsed file, or None when it is missing or not valid JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
