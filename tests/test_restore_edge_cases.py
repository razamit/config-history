"""Restore edge cases: hostile tracked lists, symlinked files, file and folder
swaps, and status after pulling a wider snapshot."""

import io
import json
import os
import zipfile

import pytest

from claude_cfg import core
from claude_cfg.errors import RestoreConflictError, UnsafeSnapshotEntryError
from claude_cfg.paths import backups_dir, claude_dir, state_file
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, store_raw_zip, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/", "plugins/"]}


def v4_zip(files: dict[str, str], tracked: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 4, "id": 1, "timestamp": "2026-01-01T00:00:00Z", "message": "x",
            "machine": "evil", "files": list(files), "tracked": tracked,
        }))
    return buffer.getvalue()


def test_roots_only_the_snapshot_names_are_never_deleted_from():
    provider = MemoryProvider()
    write_files(claude_dir(), {
        "history.jsonl": "h", "file-history/a/b": "x", "plans/p.md": "x", "CLAUDE.md": "mine",
        "skills/local.md": "mine",
    })
    tracked = ["history.jsonl", "file-history", "plans", "CLAUDE.md", "skills"]
    store_raw_zip(provider, v4_zip({"CLAUDE.md": "mine", "plans/new.md": "n"}, tracked))
    prepared = core.prepare_pull(None, CFG, provider, exact=True)
    assert prepared.plan.tracked_roots == ["CLAUDE.md", "skills"]
    assert prepared.plan.to_delete == ["skills/local.md"]
    assert prepared.plan.to_create == ["plans/new.md"]


def test_symlinked_file_pointing_outside_is_left_untouched(tmp_path):
    provider = MemoryProvider()
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "CLAUDE.md").write_text("# v1")
    write_files(claude_dir(), {"skills/a.md": "a"})
    os.symlink(dotfiles / "CLAUDE.md", claude_dir() / "CLAUDE.md")
    core.push("one", CFG, provider)
    (dotfiles / "CLAUDE.md").write_text("# v2 local edit")
    (claude_dir() / "skills/a.md").write_text("changed")

    result = core.pull(1, CFG, provider, exact=True, command_runner=None)
    assert (dotfiles / "CLAUDE.md").read_text() == "# v2 local edit"
    assert (claude_dir() / "CLAUDE.md").is_symlink()
    assert (claude_dir() / "skills/a.md").read_text() == "a"
    reason = result["left_untouched"]["CLAUDE.md"]
    assert reason.startswith("left untouched, it is a symlink to ") and "dotfiles" in reason


def test_traversal_entry_is_still_refused_before_any_write(tmp_path):
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "mine"})
    store_raw_zip(provider, v4_zip({"CLAUDE.md": "theirs", "../escape.md": "x"}, ["CLAUDE.md"]))
    with pytest.raises(UnsafeSnapshotEntryError):
        core.pull(None, CFG, provider)
    assert (claude_dir() / "CLAUDE.md").read_text() == "mine"


@pytest.mark.parametrize("local_files, snapshot_files", [
    ({"skills/zeta/inner.md": "x"}, {"skills/zeta": "now a file"}),
    ({"skills/zeta": "a file"}, {"skills/zeta/inner.md": "now a folder"}),
])
def test_file_and_folder_swap_stops_before_anything_is_written(tmp_path, local_files, snapshot_files):
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "local", **local_files})
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "remote", **snapshot_files})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "two")
    prepared = core.prepare_pull(None, CFG, provider)
    assert len(prepared.plan.conflicts) == 1 and "skills/zeta" in prepared.plan.conflicts[0]
    with pytest.raises(RestoreConflictError, match="skills/zeta"):
        core.pull(None, CFG, provider)
    assert (claude_dir() / "CLAUDE.md").read_text() == "local"
    assert not state_file().exists()
    assert not backups_dir().exists()


def test_status_after_pulling_a_wider_snapshot_shows_no_phantom_removals(tmp_path):
    provider = MemoryProvider()
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "v2", "hooks/x.sh": "echo"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "hooks/"], "two")
    core.pull(None, CFG, provider)
    status = core.status(CFG)
    assert not status.local_changes.has_changes
    (claude_dir() / "hooks/x.sh").unlink()
    assert core.status(CFG).local_changes.removed == ["hooks/x.sh"]
