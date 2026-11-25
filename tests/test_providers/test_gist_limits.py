"""The Gist API's listing and file-size limits, with requests mocked out."""

import base64
from unittest.mock import MagicMock

import pytest

from claude_cfg.errors import BackendLimitError
from claude_cfg.providers.gist import GistProvider
from claude_cfg.snapshot_store import SnapshotStore
from tests.sync_helpers import build_v3_zip


def _provider(gist_body: dict, raw_text: str = "") -> GistProvider:
    provider = GistProvider({"gist": {"token": "t", "gist_id": "abc"}})
    requests = MagicMock()

    def get(url, headers=None, timeout=None):
        response = MagicMock()
        response.json.return_value = gist_body
        response.text = raw_text
        return response

    requests.get.side_effect = get
    provider._requests = requests
    return provider


def test_truncated_listing_raises_a_clear_error():
    provider = _provider({"truncated": True, "files": {"snapshots__001_x.zip": {"raw_url": "u"}}})
    with pytest.raises(BackendLimitError, match="cannot list more than 300 snapshots"):
        provider.list_keys("snapshots/")


def test_truncated_file_is_fetched_in_full_from_raw_url():
    content = b"PK" + b"x" * 2_000_000
    files = {"snapshots__001_x.zip": {"raw_url": "https://raw/u", "truncated": True, "size": 2_700_000,
                                      "content": "cut"}}
    provider = _provider({"files": files}, raw_text=base64.b64encode(content).decode())
    assert provider.download("snapshots/001_x.zip") == content
    assert provider._requests.get.call_args_list[-1].args[0] == "https://raw/u"


def test_file_over_ten_megabytes_raises_a_clear_error():
    files = {"snapshots__001_x.zip": {"raw_url": "u", "truncated": True, "size": 11 * 1024 * 1024}}
    with pytest.raises(BackendLimitError, match="larger than 10 MB"):
        _provider({"files": files}).download("snapshots/001_x.zip")


def _full_gist(count: int = 300, truncated: bool = False) -> dict:
    files = {f"snapshots__{i:03d}_20260101T000000_x_aaaaaa.zip": {"raw_url": "u"} for i in range(1, count)}
    files["index.json"] = {"raw_url": "u"}
    return {"files": files, "truncated": truncated}


def test_upload_of_a_new_file_to_a_full_gist_is_refused_before_sending():
    provider = _provider(_full_gist())
    with pytest.raises(BackendLimitError, match="at most 300 files"):
        provider.upload("snapshots/300_20260101T000000_x_aaaaaa.zip", b"zip")
    provider._requests.patch.assert_not_called()


def test_a_full_gist_can_still_replace_an_existing_file():
    provider = _provider(_full_gist())
    provider.upload("index.json", b"{}")
    provider._requests.patch.assert_called_once()


def test_upload_to_a_gist_with_a_cut_short_listing_is_refused():
    provider = _provider(_full_gist(count=5, truncated=True))
    with pytest.raises(BackendLimitError, match="at most 300 files"):
        provider.upload("index.json", b"{}")
    provider._requests.patch.assert_not_called()


def test_push_to_a_full_gist_is_refused_before_anything_is_uploaded():
    provider = _provider(_full_gist())
    with pytest.raises(BackendLimitError, match="nothing was pushed"):
        SnapshotStore(provider).store_zip(lambda snapshot_id: build_v3_zip({"CLAUDE.md": "x"}))
    provider._requests.patch.assert_not_called()


def test_upload_that_could_not_be_downloaded_again_is_refused():
    provider = _provider({"files": {}})
    content = b"x" * (8 * 1024 * 1024)
    with pytest.raises(BackendLimitError, match=r"10\.7 MB .* over the 10 MB"):
        provider.upload("snapshots/001_x.zip", content)
    provider._requests.patch.assert_not_called()


def test_delete_works_on_a_full_gist():
    provider = _provider(_full_gist(truncated=True))
    provider._requests.patch.return_value.status_code = 200
    provider.delete("snapshots/001_20260101T000000_x_aaaaaa.zip")
    sent = provider._requests.patch.call_args.kwargs["json"]
    assert sent == {"files": {"snapshots__001_20260101T000000_x_aaaaaa.zip": None}}


def test_delete_of_a_file_past_a_cut_short_listing_tolerates_not_found():
    provider = _provider(_full_gist(count=5, truncated=True))
    provider._requests.patch.return_value.status_code = 422
    provider._requests.patch.return_value.raise_for_status.side_effect = RuntimeError("422")
    provider.delete("snapshots/999_20260101T000000_x_aaaaaa.zip")
