"""Snapshots stored as files in one secret GitHub Gist.

The Gist API returns at most 300 files per gist and at most 1 MB of each
file's content inline. Downloads always go through ``raw_url``, which serves
the full file up to 10 MB. Past either limit the API cannot serve the data
(only a git clone can), so this backend raises a clear error instead.

Both limits are checked before an upload: a new file is refused when the
gist already holds 300 files, and any file is refused when its stored
(base64) form is over 10 MB, since it could not be downloaded again.
Deleting never needs the full listing, so old snapshots can always be
removed from a full gist.
"""

import base64

from claude_cfg.errors import BackendLimitError
from claude_cfg.providers.base import StorageProvider

_API = "https://api.github.com/gists"
RAW_URL_LIMIT_BYTES = 10 * 1024 * 1024
MAX_GIST_FILES = 300
_MEGABYTE = 1024 * 1024
FILE_LIMIT_MESSAGE = (
    "The Gist backend holds at most 300 files (snapshots plus index.json) and this "
    "gist is full, so nothing was pushed. Move to another backend, or delete old "
    "snapshots from the gist."
)
LISTING_LIMIT_MESSAGE = (
    "The Gist backend cannot list more than 300 snapshots: GitHub returns only the "
    "first 300 files of a gist. Move to another backend, or delete old snapshots "
    "from the gist."
)


class GistProvider(StorageProvider):

    def __init__(self, cfg: dict) -> None:
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests required for Gist. Install: pip install claude-cfg[gist]"
            )
        self._requests = requests
        gist_cfg = cfg.get("gist", {})
        self._token = gist_cfg["token"]
        self._gist_id = gist_cfg.get("gist_id", "")
        self._headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
        }

    def _fetch_listing(self) -> tuple[dict, bool]:
        """The gist's files and whether GitHub cut the list short."""
        if not self._gist_id:
            return {}, False
        r = self._requests.get(
            f"{_API}/{self._gist_id}", headers=self._headers, timeout=30
        )
        r.raise_for_status()
        body = r.json()
        return body.get("files", {}), bool(body.get("truncated"))

    def _fetch_files(self) -> dict:
        files, truncated = self._fetch_listing()
        if truncated:
            raise BackendLimitError(LISTING_LIMIT_MESSAGE)
        return files

    def _check_upload_limits(self, key: str, file_name: str, stored_size: int) -> None:
        if stored_size > RAW_URL_LIMIT_BYTES:
            raise BackendLimitError(
                f"{key} would be {stored_size / _MEGABYTE:.1f} MB in the gist (base64), over "
                f"the {RAW_URL_LIMIT_BYTES // _MEGABYTE} MB the Gist API can serve back, so it "
                "was not uploaded. Move to another backend for snapshots this large."
            )
        files, truncated = self._fetch_listing()
        if truncated or (file_name not in files and len(files) >= MAX_GIST_FILES):
            raise BackendLimitError(FILE_LIMIT_MESSAGE)

    def _file_key(self, key: str) -> str:
        return key.replace("/", "__")

    def upload(self, key: str, content: bytes) -> None:
        encoded = base64.b64encode(content).decode("ascii")
        file_name = self._file_key(key)
        self._check_upload_limits(key, file_name, len(encoded))
        payload: dict = {"files": {file_name: {"content": encoded}}}

        if self._gist_id:
            r = self._requests.patch(
                f"{_API}/{self._gist_id}",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        else:
            payload["public"] = False
            payload["description"] = "claude-cfg snapshot store"
            r = self._requests.post(
                _API, headers=self._headers, json=payload, timeout=30
            )
            self._gist_id = r.json()["id"]

        r.raise_for_status()

    def download(self, key: str) -> bytes:
        files = self._fetch_files()
        file_name = self._file_key(key)
        if file_name not in files:
            raise FileNotFoundError(f"Key not found in Gist: {key}")
        entry = files[file_name]
        # Inline content stops at 1 MB, so the full file always comes from
        # raw_url, which itself stops at 10 MB.
        if entry.get("truncated") and int(entry.get("size") or 0) > RAW_URL_LIMIT_BYTES:
            raise BackendLimitError(
                f"{key} is larger than 10 MB, which the Gist API cannot serve. "
                "Move to another backend for snapshots this large."
            )
        raw_url = entry["raw_url"]
        r = self._requests.get(raw_url, headers=self._headers, timeout=30)
        r.raise_for_status()
        return base64.b64decode(r.text)

    def list_keys(self, prefix: str = "") -> list[str]:
        files = self._fetch_files()
        result = []
        for name in files:
            key = name.replace("__", "/")
            if not prefix or key.startswith(prefix):
                result.append(key)
        return result

    def exists(self, key: str) -> bool:
        files = self._fetch_files()
        return self._file_key(key) in files

    def delete(self, key: str) -> None:
        """Works on a full gist too: a file missing from a cut-short listing
        is still asked for by name, and "not found" is not an error."""
        file_name = self._file_key(key)
        if not self._gist_id:
            return
        files, truncated = self._fetch_listing()
        if file_name not in files and not truncated:
            return
        # The Gist API removes a file when its entry is set to null.
        r = self._requests.patch(
            f"{_API}/{self._gist_id}",
            headers=self._headers,
            json={"files": {file_name: None}},
            timeout=30,
        )
        if file_name not in files and r.status_code in (404, 422):
            return
        r.raise_for_status()

    @property
    def gist_id(self) -> str:
        return self._gist_id
