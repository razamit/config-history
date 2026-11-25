"""A backend written by claude-cfg 0.2 keeps working after the upgrade."""

import json

from claude_cfg import core
from claude_cfg import snapshot as snap
from claude_cfg.snapshot_index import INDEX_KEY
from tests.memory_provider import MemoryProvider

CFG = {"storage": "local", "tracked": ["CLAUDE.md"]}
LEGACY_KEYS = [
    "snapshots/001_20260101T000000_first.zip",
    "snapshots/002_20260102T000000_second.zip",
]


def _legacy_provider(tmp_path) -> MemoryProvider:
    source = tmp_path / "old-machine"
    source.mkdir()
    (source / "CLAUDE.md").write_text("# legacy")
    provider = MemoryProvider()
    rows = []
    for snapshot_id, key in enumerate(LEGACY_KEYS, 1):
        message = key.split("_")[-1].removesuffix(".zip")
        provider.upload(key, snap.create_zip(["CLAUDE.md"], source, snapshot_id, message))
        row = {"id": snapshot_id, "timestamp": "x", "message": message, "machine": "old-box"}
        if snapshot_id == 2:
            row["key"] = key  # 0.2 wrote "key"; very early indexes did not
        rows.append(row)
    provider.upload(INDEX_KEY, json.dumps({"snapshots": rows}).encode())
    return provider


def test_list_and_pull_legacy_snapshots(tmp_path, isolated_home):
    provider = _legacy_provider(tmp_path)
    listed = core.list_snapshots(provider)
    assert [(s["id"], s["message"], s["machine"]) for s in listed] == [
        (2, "second", "old-box"),
        (1, "first", "old-box"),
    ]
    pulled = core.pull(1, CFG, provider)
    assert pulled["key"] == LEGACY_KEYS[0]
    assert (isolated_home / ".claude" / "CLAUDE.md").read_text() == "# legacy"


def test_new_push_continues_numbering_and_keeps_old_cache_rows(tmp_path, isolated_home):
    provider = _legacy_provider(tmp_path)
    claude = isolated_home / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# new")

    pushed = core.push("third", CFG, provider)
    assert pushed["id"] == 3

    rows = json.loads(provider.download(INDEX_KEY))["snapshots"]
    assert [(row["id"], row["key"]) for row in rows] == [
        (1, LEGACY_KEYS[0]),
        (2, LEGACY_KEYS[1]),
        (3, pushed["key"]),
    ]
