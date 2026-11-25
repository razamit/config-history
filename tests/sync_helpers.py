"""Small helpers shared by the restore, backup and status tests."""

import io
import json
import zipfile
from pathlib import Path

from claude_cfg import snapshot as snap
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.snapshot_store import SnapshotStore


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative_path, text in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def read_tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` with its bytes, for before and after checks."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def push_from_other_machine(
    provider, claude_dir: Path, tracked: list[str], message: str
) -> SnapshotEntry:
    """Store a snapshot the way another machine would, without touching local state."""
    stored = SnapshotStore(provider).store_zip(
        lambda snapshot_id: snap.create_zip(tracked, claude_dir, snapshot_id, message)
    )
    return stored.entry


def build_v3_zip(files: dict[str, str], message: str = "old") -> bytes:
    """A schema v3 snapshot: no tracked list and no hashes in the manifest."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for relative_path, text in files.items():
            archive.writestr(relative_path, text)
        manifest = {
            "schema_version": 3,
            "id": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            "message": message,
            "machine": "old-box",
            "source_platform": "linux",
            "source_home": "${HOME}",
            "files": list(files),
        }
        archive.writestr("manifest.json", json.dumps(manifest))
    return buffer.getvalue()


def store_raw_zip(provider, zip_bytes: bytes) -> SnapshotEntry:
    return SnapshotStore(provider).store_zip(lambda snapshot_id: zip_bytes).entry
