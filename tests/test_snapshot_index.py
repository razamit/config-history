import json

from claude_cfg import snapshot as snap
from claude_cfg.snapshot_index import INDEX_KEY, UNKNOWN_MACHINE, SnapshotIndexManager
from claude_cfg.snapshot_keys import format_snapshot_key, parse_snapshot_key
from tests.memory_provider import MemoryProvider

NEW_KEY = "snapshots/004_20260506T143200_added-new-osint_a1b2c3.zip"
OLD_KEY = "snapshots/002_20260101T000000_first-try.zip"
ENC_KEY = "snapshots/005_20260507T080000_secret-stuff_0f0f0f.zip.enc"


# --- key format ---------------------------------------------------------------

def test_format_and_parse_round_trip():
    key = format_snapshot_key(4, "2026-05-06T14:32:00Z", "Added new OSINT", "a1b2c3", False)
    assert key == NEW_KEY
    parsed = parse_snapshot_key(key)
    assert parsed.snapshot_id == 4
    assert parsed.timestamp == "2026-05-06T14:32:00Z"
    assert parsed.slug == "added-new-osint"
    assert parsed.encrypted is False


def test_encrypted_keys_use_zip_enc_suffix():
    key = format_snapshot_key(5, "2026-05-07T08:00:00Z", "secret stuff", "0f0f0f", True)
    assert key == ENC_KEY
    assert parse_snapshot_key(key).encrypted is True


def test_empty_message_gets_default_slug():
    key = format_snapshot_key(1, "2026-01-01T00:00:00Z", "!!!", "abcdef", False)
    assert "_snapshot_abcdef.zip" in key
    assert "__" not in key  # Gist maps "/" to "__", so a double underscore would break it


def test_old_format_keys_parse():
    parsed = parse_snapshot_key(OLD_KEY)
    assert parsed.snapshot_id == 2
    assert parsed.slug == "first-try"
    assert parse_snapshot_key("snapshots/003_20260101T000000_.zip").slug == ""


def test_unparseable_keys_return_none():
    for key in (
        "snapshots/.DS_Store",
        "snapshots/notes.txt",
        "snapshots/001_20260101T000000_x (conflicted copy).zip",
        "index.json",
    ):
        assert parse_snapshot_key(key) is None


# --- index rebuild ----------------------------------------------------------

def _zip_bytes(tmp_path, message="from manifest"):
    claude = tmp_path / "src"
    claude.mkdir(exist_ok=True)
    (claude / "CLAUDE.md").write_text("# hi")
    return snap.create_zip(["CLAUDE.md"], claude, 1, message)


def _write_cache(provider, rows):
    provider.upload(INDEX_KEY, json.dumps({"snapshots": rows}).encode())


def test_entries_come_from_keys_and_unparseable_keys_are_ignored():
    provider = MemoryProvider()
    provider.upload(NEW_KEY, b"not a zip")
    provider.upload(OLD_KEY, b"not a zip")
    provider.upload("snapshots/.DS_Store", b"")
    entries = SnapshotIndexManager(provider).load_entries()
    assert [e.snapshot_id for e in entries] == [2, 4]


def test_missing_cache_falls_back_to_slug_and_unknown_machine():
    provider = MemoryProvider()
    provider.upload(NEW_KEY, b"not a zip, so manifest repair fails quietly")
    entry = SnapshotIndexManager(provider).load_entries()[0]
    assert entry.message == "added new osint"
    assert entry.machine == UNKNOWN_MACHINE
    assert entry.metadata_known is False


def test_missing_cache_is_repaired_from_plain_manifest(tmp_path):
    provider = MemoryProvider()
    provider.upload(NEW_KEY, _zip_bytes(tmp_path, "real message"))
    entry = SnapshotIndexManager(provider).load_entries()[0]
    assert entry.message == "real message"
    assert entry.machine not in ("", UNKNOWN_MACHINE)
    assert entry.metadata_known is True


def test_encrypted_snapshots_are_never_downloaded_for_repair():
    provider = MemoryProvider()
    provider.upload(ENC_KEY, b"CCFGENC2...")
    downloads = []
    original_download = provider.download
    provider.download = lambda key: downloads.append(key) or original_download(key)
    entry = SnapshotIndexManager(provider).load_entries()[0]
    assert ENC_KEY not in downloads
    assert entry.machine == UNKNOWN_MACHINE


def test_cache_metadata_is_merged_by_key_and_stale_rows_dropped():
    provider = MemoryProvider()
    provider.upload(NEW_KEY, b"zip")
    _write_cache(provider, [
        {"id": 4, "timestamp": "x", "message": "cached msg", "machine": "laptop", "key": NEW_KEY},
        {"id": 9, "timestamp": "x", "message": "gone", "machine": "m", "key": "snapshots/009_x.zip"},
    ])
    manager = SnapshotIndexManager(provider)
    entries = manager.load_entries()
    assert [(e.message, e.machine) for e in entries] == [("cached msg", "laptop")]

    manager.save_cache(entries)
    rows = json.loads(provider.download(INDEX_KEY))["snapshots"]
    assert [row["key"] for row in rows] == [NEW_KEY]


def test_old_cache_rows_without_key_match_by_id():
    provider = MemoryProvider()
    provider.upload(OLD_KEY, b"zip")
    _write_cache(provider, [{"id": 2, "timestamp": "x", "message": "old", "machine": "desk"}])
    entry = SnapshotIndexManager(provider).load_entries()[0]
    assert (entry.key, entry.message, entry.machine) == (OLD_KEY, "old", "desk")


def test_corrupt_cache_is_treated_as_empty():
    provider = MemoryProvider()
    provider.upload(NEW_KEY, b"zip")
    provider.upload(INDEX_KEY, b"{not json")
    assert len(SnapshotIndexManager(provider).load_entries()) == 1


def test_save_cache_skips_entries_without_known_metadata():
    provider = MemoryProvider()
    provider.upload(NEW_KEY, b"not a zip")
    manager = SnapshotIndexManager(provider)
    manager.save_cache(manager.load_entries())
    assert json.loads(provider.download(INDEX_KEY))["snapshots"] == []
