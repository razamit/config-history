"""Exact restore: what a pull writes and every rule that limits deletion."""

import os

import pytest

from claude_cfg import core
from claude_cfg.errors import UnsafeSnapshotEntryError
from claude_cfg.paths import backups_dir, claude_dir
from claude_cfg.restore_writer import SafeDeleter
from claude_cfg.tracked_files import normalize_root, safe_roots
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import build_v3_zip, push_from_other_machine, store_raw_zip, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/", "plugins/"]}


@pytest.fixture
def provider():
    return MemoryProvider()


@pytest.fixture
def pushed(provider):
    """Snapshot #1 holds CLAUDE.md, one skill and a plugin manifest."""
    write_files(claude_dir(), {
        "CLAUDE.md": "# one",
        "skills/keep.md": "keep",
        "plugins/installed_plugins.json": "{}",
    })
    core.push("one", CFG, provider)
    return provider


def test_pull_leaves_unchanged_files_untouched(pushed):
    old_time = 1_000_000_000
    for path in claude_dir().rglob("*"):
        if path.is_file():
            os.utime(path, (old_time, old_time))
    result = core.pull(None, CFG, pushed)
    assert result["files_restored"] == 0 and result["unchanged"] == 3
    assert all(p.stat().st_mtime == old_time for p in claude_dir().rglob("*") if p.is_file())


def test_exact_pull_returns_to_the_snapshot(pushed):
    write_files(claude_dir(), {"skills/new/extra.md": "x", "CLAUDE.md": "# edited"})
    result = core.pull(1, CFG, pushed, exact=True)
    assert result["deleted"] == 1 and result["overwritten"] == 1
    assert not (claude_dir() / "skills/new").exists()
    assert (claude_dir() / "CLAUDE.md").read_text() == "# one"


def test_overlay_pull_keeps_local_extras(pushed):
    write_files(claude_dir(), {"skills/extra.md": "x"})
    result = core.pull(1, CFG, pushed)
    assert result["kept_local"] == 1
    assert (claude_dir() / "skills/extra.md").exists()


def test_exact_pull_never_deletes_excluded_paths(pushed):
    excluded = [
        ".credentials.json", "projects/p/chat.jsonl", "plugins/cache/a/big.js",
        "plugins/marketplaces/m/.git/HEAD", "skills/tool/.git/config",
        "skills/tool/node_modules/dep/index.js", "skills/debug.log", "skills/.DS_Store",
    ]
    write_files(claude_dir(), {path: "x" for path in excluded})
    prepared = core.prepare_pull(1, CFG, pushed, exact=True)
    assert prepared.plan.to_delete == []
    core.pull(1, CFG, pushed, exact=True)
    assert all((claude_dir() / path).exists() for path in excluded)


def test_exact_pull_never_deletes_outside_tracked_roots(pushed):
    write_files(claude_dir(), {"agents/mine.md": "x", "notes.txt": "x"})
    core.pull(1, CFG, pushed, exact=True)
    assert (claude_dir() / "agents/mine.md").exists()
    assert (claude_dir() / "notes.txt").exists()


def test_safe_deleter_refuses_each_unsafe_path(tmp_path):
    target = tmp_path / ".claude"
    write_files(target, {".credentials.json": "x", "agents/a.md": "x", "skills/ok.md": "x"})
    deleter = SafeDeleter(target, ["skills", ".credentials.json"])
    assert deleter.delete(".credentials.json") is False
    assert deleter.delete("agents/a.md") is False
    assert deleter.delete("skills/../agents/a.md") is False
    assert deleter.delete("skills/ok.md") is True
    assert (target / ".credentials.json").exists() and (target / "agents/a.md").exists()


def test_tracked_roots_from_a_snapshot_cannot_escape():
    assert normalize_root("../outside") is None
    assert normalize_root("/etc") is None
    assert normalize_root("C:/Windows") is None
    assert normalize_root("./") is None
    assert safe_roots(["skills/", "skills", "../x", "agents/./a"]) == ["skills", "agents/a"]


def test_symlink_out_of_target_is_never_followed(tmp_path, pushed):
    outside = tmp_path / "outside"
    write_files(outside, {"precious.md": "keep me", "folder/inner.md": "keep me too"})
    os.symlink(outside / "precious.md", claude_dir() / "skills" / "link.md")
    os.symlink(outside / "folder", claude_dir() / "skills" / "linked-folder")
    deleter = SafeDeleter(claude_dir(), ["skills"])
    assert deleter.delete("skills/link.md") is False
    assert deleter.delete("skills/linked-folder/inner.md") is False

    core.pull(1, CFG, pushed, exact=True)
    assert (outside / "precious.md").read_text() == "keep me"
    assert (outside / "folder" / "inner.md").read_text() == "keep me too"


def test_symlinked_root_pointing_outside_is_not_emptied(tmp_path, provider):
    """The snapshot and this machine both track skills/, and skills/ here is a
    symlink out of the folder. An exact pull must neither delete what is
    behind it nor write through it."""
    source = tmp_path / "source" / ".claude"
    write_files(source, {"CLAUDE.md": "# two", "skills/new.md": "from snapshot"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "two")
    outside = tmp_path / "outside-skills"
    write_files(outside, {"theirs.md": "x"})
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    os.symlink(outside, claude_dir() / "skills")

    prepared = core.prepare_pull(None, CFG, provider, exact=True)
    assert "skills" in prepared.plan.tracked_roots
    assert prepared.plan.to_delete == []
    result = core.pull(None, CFG, provider, exact=True)
    assert (outside / "theirs.md").exists()
    assert not (outside / "new.md").exists()
    assert "skills/new.md" in result["left_untouched"]
    assert (claude_dir() / "CLAUDE.md").read_text() == "# two"


def test_emptied_folders_are_removed_but_never_a_root(pushed):
    write_files(claude_dir(), {"skills/a/b/only.md": "x"})
    (claude_dir() / "skills" / "keep.md").unlink()
    deleter = SafeDeleter(claude_dir(), ["skills"])
    assert deleter.delete("skills/a/b/only.md")
    assert not (claude_dir() / "skills" / "a").exists()
    assert (claude_dir() / "skills").is_dir()


def test_traversal_entry_fails_the_pull_before_any_write(provider):
    store_raw_zip(provider, build_v3_zip({"CLAUDE.md": "x", "../escape.md": "x"}))
    with pytest.raises(UnsafeSnapshotEntryError):
        core.pull(None, CFG, provider)
    assert not (claude_dir() / "CLAUDE.md").exists()
    assert not (claude_dir().parent / "escape.md").exists()


def test_write_through_symlink_out_of_target_is_left_untouched(tmp_path, provider):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    write_files(claude_dir(), {"CLAUDE.md": "# one"})
    source = tmp_path / "source" / ".claude"
    write_files(source, {"skills/a.md": "new", "CLAUDE.md": "# two"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "two")
    os.symlink(outside, claude_dir() / "skills")
    result = core.pull(None, CFG, provider)
    assert not (outside / "a.md").exists()
    assert (claude_dir() / "CLAUDE.md").read_text() == "# two"
    assert "symlink to" in result["left_untouched"]["skills/a.md"]
