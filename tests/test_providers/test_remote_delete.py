"""delete() on the network backends, with their clients mocked out."""

from unittest.mock import MagicMock, patch

import pytest

from claude_cfg.providers.gist import GistProvider
from claude_cfg.providers.s3 import S3Provider
from claude_cfg.providers.sftp import SFTPProvider


def test_s3_delete_calls_delete_object():
    client = MagicMock()
    cfg = {"storage": "s3", "s3": {"access_key": "a", "secret_key": "b", "bucket": "bkt"}}
    with patch("boto3.client", return_value=client):
        provider = S3Provider(cfg)
    provider.delete("snapshots/001_x.zip")
    client.delete_object.assert_called_once_with(Bucket="bkt", Key="snapshots/001_x.zip")


def _gist_provider(gist_id: str, file_names: list[str]) -> GistProvider:
    provider = GistProvider({"gist": {"token": "t", "gist_id": gist_id}})
    requests = MagicMock()
    requests.get.return_value.json.return_value = {
        "files": {name: {"raw_url": "u"} for name in file_names}
    }
    provider._requests = requests
    return provider


def test_gist_delete_sets_file_to_null():
    provider = _gist_provider("abc", ["snapshots__001_x.zip"])
    provider.delete("snapshots/001_x.zip")
    _, kwargs = provider._requests.patch.call_args
    assert kwargs["json"] == {"files": {"snapshots__001_x.zip": None}}


@pytest.mark.parametrize("gist_id, files", [("abc", []), ("", [])], ids=["missing-file", "no-gist"])
def test_gist_delete_missing_is_not_an_error(gist_id, files):
    provider = _gist_provider(gist_id, files)
    provider.delete("snapshots/001_x.zip")
    provider._requests.patch.assert_not_called()


def _sftp_provider() -> SFTPProvider:
    provider = SFTPProvider.__new__(SFTPProvider)
    provider._remote_root = "/srv/cfg"
    provider._sftp = MagicMock()
    return provider


def test_sftp_delete_removes_remote_file():
    provider = _sftp_provider()
    provider.delete("snapshots/001_x.zip")
    provider._sftp.remove.assert_called_once_with("/srv/cfg/snapshots/001_x.zip")


def test_sftp_delete_missing_is_not_an_error():
    provider = _sftp_provider()
    provider._sftp.remove.side_effect = FileNotFoundError("gone")
    provider.delete("snapshots/001_x.zip")
