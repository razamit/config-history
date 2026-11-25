"""An in-memory storage provider for tests."""

from claude_cfg.providers.base import StorageProvider


class MemoryProvider(StorageProvider):
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def upload(self, key: str, content: bytes) -> None:
        self._store[key] = content

    def download(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    def list_keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]

    def exists(self, key: str) -> bool:
        return key in self._store

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
