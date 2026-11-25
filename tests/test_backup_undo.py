"""Precise backups before a pull, undo, and pruning."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from claude_cfg import core
from claude_cfg.backup_manager import MANIFEST_NAME, BackupManager
from claude_cfg.errors import LegacyBackupError, NothingToUndoError, UndoConflictError
from claude_cfg.paths import backups_dir, claude_dir, state_file
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import read_tree, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/", "plugins/"]}


@pytest.fixture
def provider():
    """Snapshot #1 is pushed; the working copy then moves on to snapshot #2."""
    provider = MemoryProvider()
    write_files(claude_dir(), {
        "CLAUDE.md": "# one", "skills/a.md": "a", "skills/gone.md": "g",
        "plugins/installed_plugins.json": "{}",
    })
    core.push("one", CFG, provider)
    (claude_dir() / "skills/gone.md").unlink()
    write_files(claude_dir(), {"CLAUDE.md": "# two", "skills/new.md": "n"})
    core.push("two", CFG, provider)
    return provider


def _backup_folders():
    return sorted(p for p in backups_dir().iterdir() if p.is_dir()) if backups_dir().exists() else []


def test_backup_holds_only_files_the_pull_replaces(provider):
    write_files(claude_dir(), {f"plugins/cache/p/file{i}.js": "big" for i in range(5)})
    write_files(claude_dir(), {"skills/.git/HEAD": "ref"})
    result = core.pull(1, CFG, provider, exact=True)

    backup = _backup_folders()[0]
    assert str(backup) == result["backup_dir"]
    saved = read_tree(backup / "files")
    assert saved == {"CLAUDE.md": b"# two", "skills/new.md": b"n"}
    manifest = json.loads((backup / MANIFEST_NAME).read_text())
    assert manifest["overwritten"] == ["CLAUDE.md"]
    assert manifest["deleted"] == ["skills/new.md"]
    assert manifest["created"] == ["skills/gone.md"]
    assert set(manifest["written_hashes"]) == {"CLAUDE.md", "skills/gone.md"}
    assert manifest["snapshot_id"] == 1 and manifest["previous_state"]["snapshot_id"] == 2


def test_pull_that_changes_nothing_makes_no_backup(provider):
    result = core.pull(2, CFG, provider, exact=True)
    assert result["backup_dir"] is None
    assert _backup_folders() == []


def test_undo_round_trip_for_overwrite_create_and_delete(provider):
    before = read_tree(claude_dir())
    state_before = state_file().read_text()
    core.pull(1, CFG, provider, exact=True)
    assert read_tree(claude_dir()) != before

    result = core.undo()
    assert read_tree(claude_dir()) == before
    assert sorted(result.restored) == ["CLAUDE.md", "skills/new.md"]
    assert result.removed == ["skills/gone.md"]
    assert json.loads(state_file().read_text())["snapshot_id"] == 2
    assert json.loads(state_file().read_text()) == json.loads(state_before)
    manifest = json.loads((_backup_folders()[0] / MANIFEST_NAME).read_text())
    assert manifest["undone_at"]
    with pytest.raises(NothingToUndoError):
        core.undo()


def test_undo_removes_state_when_there_was_none(provider):
    state_file().unlink()
    core.pull(1, CFG, provider)
    core.undo()
    assert not state_file().exists()


def test_undo_refuses_when_files_changed_after_pull(provider):
    core.pull(1, CFG, provider, exact=True)
    write_files(claude_dir(), {"CLAUDE.md": "# edited after pull", "skills/new.md": "back"})
    with pytest.raises(UndoConflictError) as conflict:
        core.undo()
    assert conflict.value.changed_files == ["CLAUDE.md", "skills/new.md"]
    assert (claude_dir() / "CLAUDE.md").read_text() == "# edited after pull"

    result = core.undo(force=True)
    assert (claude_dir() / "CLAUDE.md").read_text() == "# two"
    assert result.overridden_changes == ["CLAUDE.md", "skills/new.md"]


def test_undo_explains_a_legacy_backup(provider):
    legacy = backups_dir() / "20991231T000000Z"
    write_files(legacy, {"settings.json": "{}"})
    with pytest.raises(LegacyBackupError, match=re.escape(str(legacy))):
        core.undo()


def test_pull_prunes_to_backups_keep(provider):
    cfg = {**CFG, "backups": {"keep": "2"}}
    for _ in range(2):
        core.pull(1, cfg, provider)
        core.pull(2, cfg, provider)
    folders = _backup_folders()
    assert len(folders) == 2
    assert [json.loads((f / MANIFEST_NAME).read_text())["snapshot_id"] for f in folders] == [1, 2]


def test_prune_keeps_newest_and_ignores_other_folders(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = iter([start + timedelta(minutes=m) for m in range(4)])
    manager = BackupManager(tmp_path, clock=lambda: next(times))
    for _ in range(4):
        manager._new_folder()
    (tmp_path / "not-a-backup").mkdir()
    removed = manager.prune(keep=2)
    assert [p.name for p in removed] == ["20260101T000100Z", "20260101T000000Z"]
    assert (tmp_path / "not-a-backup").exists()


def test_same_second_backups_get_distinct_ordered_folders(tmp_path):
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    manager = BackupManager(tmp_path, clock=lambda: fixed)
    first, second = manager._new_folder(), manager._new_folder()
    assert second.name == "20260101T000000Z-2"
    assert [r.path for r in manager.list_backups()] == [second, first]
