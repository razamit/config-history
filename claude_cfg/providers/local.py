from pathlib import Path

from claude_cfg.private_file import make_private_dirs, write_private_bytes
from claude_cfg.providers.base import StorageProvider


class LocalProvider(StorageProvider):
    """Snapshots in a folder on this machine.

    Snapshots hold copies of settings.json and similar files, so every folder
    this provider creates is owner-only (0700) and every object it writes is
    owner-only (0600). A folder the user created beforehand keeps its mode.
    """

    def __init__(self, cfg: dict) -> None:
        self._root = Path(cfg["local"]["path"]).expanduser()
        make_private_dirs(self._root)

    def upload(self, key: str, content: bytes) -> None:
        write_private_bytes(self._root / key, content)

    def download(self, key: str) -> bytes:
        path = self._root / key
        if not path.exists():
            raise FileNotFoundError(f"Key not found in local store: {key}")
        return path.read_bytes()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self._root / prefix if prefix else self._root
        if not base.exists():
            return []
        return [
            str(p.relative_to(self._root)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file() and not p.name.endswith(".partial")
        ]

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()

    def delete(self, key: str) -> None:
        (self._root / key).unlink(missing_ok=True)
