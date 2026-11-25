"""Undo is bound to the folder the pull wrote into and to the sync state it
left, and backups keep file modes private and intact."""

import json
import os
import stat

import pytest

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.errors import UndoTargetMismatchError
from claude_cfg.paths import CLAUDE_CONFIG_DIR_ENV, backups_dir, claude_dir, config_file, state_file
from claude_cfg.private_file import write_private_json
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, read_tree, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/"]}
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_undo_refuses_a_pull_made_into_another_profile(tmp_path, monkeypatch):
    provider = MemoryProvider()
    work = tmp_path / "claude-work"
    monkeypatch.setenv(CLAUDE_CONFIG_DIR_ENV, str(work))
    write_files(work, {"CLAUDE.md": "same", "skills/work-only.md": "work secret"})
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "same"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "one")
    core.pull(None, CFG, provider, exact=True)
    monkeypatch.delenv(CLAUDE_CONFIG_DIR_ENV)
    write_files(claude_dir(), {"CLAUDE.md": "personal"})

    with pytest.raises(UndoTargetMismatchError) as raised:
        core.undo()
    assert str(work.resolve()) in str(raised.value)
    assert str(claude_dir().resolve()) in str(raised.value)
    assert read_tree(claude_dir()) == {"CLAUDE.md": b"personal"}


def test_undo_leaves_state_alone_after_a_later_push(tmp_path):
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "v1", "skills/a.md": "a"})
    core.push("one", CFG, provider)
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "v2", "skills/a.md": "a"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "two")
    core.pull(None, CFG, provider)
    write_files(claude_dir(), {"skills/new.md": "n"})
    core.push("three", CFG, provider)

    result = core.undo(force=True)
    assert result.state_restored is False
    assert json.loads(state_file().read_text())["snapshot_id"] == 3


def test_undo_restores_state_when_it_still_points_at_the_pulled_snapshot(tmp_path):
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "v1"})
    core.push("one", CFG, provider)
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "v2"})
    push_from_other_machine(provider, source, ["CLAUDE.md"], "two")
    core.pull(None, CFG, provider)
    assert core.undo().state_restored is True
    assert json.loads(state_file().read_text())["snapshot_id"] == 1


@posix_only
def test_undo_puts_back_file_modes_and_backups_are_private(tmp_path):
    provider = MemoryProvider()
    write_files(claude_dir(), {"CLAUDE.md": "x", "skills/run.sh": "#!/bin/sh", "skills/key.json": "k"})
    os.chmod(claude_dir() / "skills/run.sh", 0o755)
    os.chmod(claude_dir() / "skills/key.json", 0o600)
    source = tmp_path / "src" / ".claude"
    write_files(source, {"CLAUDE.md": "x"})
    push_from_other_machine(provider, source, ["CLAUDE.md", "skills/"], "one")
    old_umask = os.umask(0o022)
    try:
        result = core.pull(None, CFG, provider, exact=True)
        backup = backups_dir() / os.path.basename(result["backup_dir"])
        assert _mode(backups_dir()) == 0o700 and _mode(backup) == 0o700
        assert _mode(backup / "files/skills/key.json") == 0o600
        core.undo()
    finally:
        os.umask(old_umask)
    assert _mode(claude_dir() / "skills/run.sh") == 0o755
    assert _mode(claude_dir() / "skills/key.json") == 0o600


@posix_only
def test_private_files_are_created_owner_only(monkeypatch):
    created_modes = []
    real_open = os.open

    def recording_open(path, flags, mode=0o777, *args, **kwargs):
        if flags & os.O_CREAT:
            created_modes.append(mode)
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    old_umask = os.umask(0o022)
    try:
        cfg_mod.save({"storage": "local", "tracked": []})
        write_private_json(state_file(), {"a": 1})
    finally:
        os.umask(old_umask)
    assert created_modes == [0o600, 0o600]
    assert _mode(config_file()) == 0o600 and _mode(state_file()) == 0o600
