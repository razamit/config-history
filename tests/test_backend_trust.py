"""Text and metadata from the backend are never trusted as they are."""

import io
import json
import zipfile

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli import app, output
from claude_cfg.session_start_notice import MACHINE_NAME_LIMIT, newer_snapshot_message
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.sync_status import RemoteStatus
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import store_raw_zip, write_files


def _plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CLAUDE.md", "x")
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 4, "id": 1, "timestamp": "2026-01-01T00:00:00Z", "message": "m",
            "machine": "box", "files": ["CLAUDE.md"], "tracked": ["CLAUDE.md"],
        }))
    return buffer.getvalue()


def test_hook_notice_strips_control_characters_and_caps_the_machine_name():
    machine = "evil\n\x1b[2J" + "A" * 80 + "\r\x00"
    entry = SnapshotEntry(9, "2026-01-01T00:00:00Z", "snapshots/009_x.zip", "m", machine, False)
    message = newer_snapshot_message(RemoteStatus(checked=True, latest=entry, is_newer=True))
    assert all(ord(c) >= 32 and c != "\x7f" for c in message)
    shown = message.split(" from ", 1)[1].split(" (", 1)[0]
    assert len(shown) <= MACHINE_NAME_LIMIT and shown.startswith("evil[2J")


@pytest.mark.parametrize("bad_row", [
    {"id": 1, "key": ["a"]},
    {"id": 1, "key": None, "message": ["not", "text"]},
    {"id": "1", "machine": {"x": 1}},
    {"id": True},
])
def test_malformed_index_rows_are_ignored(bad_row):
    provider = MemoryProvider()
    store_raw_zip(provider, _plain_zip())
    provider.upload("index.json", json.dumps({"snapshots": [bad_row]}).encode())
    listed = core.list_snapshots(provider)
    assert [row["id"] for row in listed] == [1]
    assert listed[0]["message"] == "m"
    status = core.status({"storage": "local", "tracked": []}, provider_factory=lambda: provider)
    assert status.remote.error is None


def test_pull_and_diff_take_allow_plain_on_the_command_line(isolated_home, monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)
    store = isolated_home / "store"
    write_files(isolated_home / ".claude", {"CLAUDE.md": "# mine"})
    plain_cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(store)}}
    cfg_mod.save(plain_cfg)
    runner = CliRunner()
    assert runner.invoke(app, ["push", "plain"]).exit_code == 0
    cfg_mod.save({**plain_cfg, "encryption": {"enabled": True, "passphrase": "pw"}})

    refused = runner.invoke(app, ["diff"])
    assert refused.exit_code == 1 and "--allow-plain" in refused.output
    assert runner.invoke(app, ["diff", "--allow-plain"]).exit_code == 0
    assert runner.invoke(app, ["pull"]).exit_code == 1
    assert runner.invoke(app, ["pull", "--allow-plain"]).exit_code == 0
