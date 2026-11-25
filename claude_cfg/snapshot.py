"""Building and reading snapshot zip archives.

Schema history:
  v1  files and message only
  v2  adds machine and timestamps
  v3  adds source_platform and source_home (portable path tokens)
  v4  adds tracked, file_hashes and content_hash
"""

import io
import json
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional

from claude_cfg import __version__
from claude_cfg.content_hashing import content_hash, sha256_hex
from claude_cfg.content_transform import detokenize, native_separator, tokenize
from claude_cfg.errors import UnsafeSnapshotEntryError
from claude_cfg.external_members import is_external_member
from claude_cfg.paths import HOME_TOKEN, platform_name, resolve_python
from claude_cfg.snapshot_keys import format_snapshot_key, new_random_suffix
from claude_cfg.tracked_files import list_tracked_files

SCHEMA_VERSION = 4
MANIFEST_NAME = "manifest.json"


def snapshot_key(
    snapshot_id: int,
    timestamp: str,
    message: str,
    random_suffix: Optional[str] = None,
    encrypted: bool = False,
) -> str:
    """Object key for a new snapshot. See :mod:`claude_cfg.snapshot_keys`."""
    return format_snapshot_key(
        snapshot_id,
        timestamp,
        message,
        random_suffix or new_random_suffix(),
        encrypted,
    )


def check_member_name(name: str) -> None:
    """Refuse zip entries that are absolute or climb out with ``..``."""
    if name.startswith(("/", "\\")) or ".." in PurePosixPath(name.replace("\\", "/")).parts:
        raise UnsafeSnapshotEntryError(f"Refusing unsafe zip entry: {name!r}")
    if len(name) > 1 and name[1] == ":":
        raise UnsafeSnapshotEntryError(f"Refusing unsafe zip entry: {name!r}")


def create_zip(
    tracked: list[str],
    claude_dir: Path,
    snapshot_id: int,
    message: str,
    home: Optional[Path] = None,
    external_members: Optional[Mapping[str, bytes]] = None,
    automatic: bool = False,
) -> bytes:
    """Build a snapshot archive of the tracked files under ``claude_dir``.

    ``home`` defaults to the folder's parent (right for ``home/.claude``).
    ``external_members`` are already stored-form bytes for things that live
    outside the Claude folder, under the ``_external/`` prefix. They are
    hashed like files, so status and the sync state see them change.
    ``automatic`` marks a snapshot that auto-save made, which retention may
    delete later; a snapshot the user saved is never marked.
    """
    home = home if home is not None else claude_dir.parent
    file_hashes: dict[str, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in list_tracked_files(tracked, claude_dir):
            local_content = (claude_dir / relative_path).read_bytes()
            stored = tokenize(relative_path, local_content, home, claude_dir)
            archive.writestr(relative_path, stored)
            file_hashes[relative_path] = sha256_hex(stored)
        for member_name, stored in sorted((external_members or {}).items()):
            archive.writestr(member_name, stored)
            file_hashes[member_name] = sha256_hex(stored)
        manifest = _build_manifest(snapshot_id, message, list(tracked), file_hashes, automatic)
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
    return buf.getvalue()


def _build_manifest(
    snapshot_id: int,
    message: str,
    tracked: list[str],
    file_hashes: dict[str, str],
    automatic: bool = False,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": snapshot_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "message": message,
        "machine": socket.gethostname(),
        "source_platform": platform_name(),
        "source_home": HOME_TOKEN,
        "claude_cfg_version": __version__,
        "files": list(file_hashes),
        "tracked": tracked,
        "file_hashes": file_hashes,
        "content_hash": content_hash(file_hashes),
        "automatic": automatic,
    }


def extract_zip(zip_bytes: bytes, claude_dir: Path) -> list[str]:
    """Write every file in the archive into ``claude_dir``. Overlay only.

    Pull goes through a restore plan instead; this stays for callers that
    want a plain extraction.
    """
    home = claude_dir.parent
    python = resolve_python()
    extracted: list[str] = []
    base = claude_dir.resolve()
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as archive:
        for name in archive.namelist():
            if name == MANIFEST_NAME or is_external_member(name):
                continue
            check_member_name(name)
            dest = (claude_dir / name).resolve()
            if not dest.is_relative_to(base):
                raise UnsafeSnapshotEntryError(f"Refusing unsafe zip entry: {name!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = detokenize(name, archive.read(name), home, native_separator(), python)
            dest.write_bytes(content)
            extracted.append(name)
    return extracted


def read_manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as archive:
        return json.loads(archive.read(MANIFEST_NAME))
