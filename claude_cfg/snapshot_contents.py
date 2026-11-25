"""A snapshot archive opened in memory: its manifest and its stored files.

Works for every schema version. Fields that only schema v4 writes
(``tracked``, ``file_hashes``, ``content_hash``) are computed from the zip
when an older snapshot lacks them, except ``tracked``, which stays None so
the caller can fall back to the local config.
"""

import io
import zipfile
from dataclasses import dataclass
from typing import Optional

from claude_cfg.content_hashing import content_hash, sha256_hex
from claude_cfg.snapshot import MANIFEST_NAME, check_member_name, read_manifest


@dataclass(frozen=True)
class SnapshotContents:
    manifest: dict
    stored_files: dict[str, bytes]

    @classmethod
    def from_zip(cls, zip_bytes: bytes) -> "SnapshotContents":
        """Read every member, refusing unsafe names before anything is used."""
        manifest = read_manifest(zip_bytes)
        stored_files: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as archive:
            for name in archive.namelist():
                if name == MANIFEST_NAME or name.endswith("/"):
                    continue
                check_member_name(name)
                stored_files[name] = archive.read(name)
        return cls(manifest=manifest, stored_files=stored_files)

    @property
    def schema_version(self) -> int:
        return int(self.manifest.get("schema_version", 1))

    @property
    def tracked(self) -> Optional[list[str]]:
        """The tracked list recorded at push, or None for schema 1 to 3."""
        tracked = self.manifest.get("tracked")
        if isinstance(tracked, list) and all(isinstance(t, str) for t in tracked):
            return tracked
        return None

    def file_hashes(self) -> dict[str, str]:
        """``{path: sha256}`` of the stored bytes, always computed from the zip.

        The manifest's own copy is not trusted for restore decisions, since
        the bytes in the archive are what actually gets written.
        """
        return {name: sha256_hex(content) for name, content in sorted(self.stored_files.items())}

    def content_hash(self) -> str:
        return content_hash(self.file_hashes())
