"""Restore plan classification, schema v4 fields and older snapshots."""

import json
from pathlib import PureWindowsPath

import pytest

from claude_cfg import core
from claude_cfg import snapshot as snap
from claude_cfg.content_hashing import content_hash, sha256_hex
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.errors import UnsafeSnapshotEntryError
from claude_cfg.paths import claude_dir
from claude_cfg.restore_plan import RestorePlanner
from claude_cfg.snapshot_contents import SnapshotContents
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import build_v3_zip, store_raw_zip, write_files


def _planner(home, python="python3", sep="/"):
    return RestorePlanner(PathTokenTransform(home=home, sep=sep, python=python))


def test_v4_manifest_records_tracked_hashes_and_content_hash(tmp_path):
    claude = tmp_path / ".claude"
    write_files(claude, {"CLAUDE.md": "# hi", "skills/a.md": "a"})
    manifest = snap.read_manifest(snap.create_zip(["CLAUDE.md", "skills/"], claude, 1, "m"))
    assert manifest["schema_version"] == 4
    assert manifest["tracked"] == ["CLAUDE.md", "skills/"]
    assert manifest["file_hashes"] == {"CLAUDE.md": sha256_hex(b"# hi"), "skills/a.md": sha256_hex(b"a")}
    assert manifest["content_hash"] == content_hash(manifest["file_hashes"])


def test_content_hash_ignores_insertion_order():
    assert content_hash({"a": "1", "b": "2"}) == content_hash({"b": "2", "a": "1"})
    assert content_hash({"a": "1"}) != content_hash({"a": "2"})


def test_file_hashes_cover_stored_tokenized_bytes(tmp_path):
    claude = tmp_path / ".claude"
    write_files(claude, {"settings.json": json.dumps({"cmd": f"{claude}/x.py"})})
    zip_bytes = snap.create_zip(["settings.json"], claude, 1, "m")
    contents = SnapshotContents.from_zip(zip_bytes)
    assert b"${CLAUDE_HOME}" in contents.stored_files["settings.json"]
    assert contents.file_hashes() == snap.read_manifest(zip_bytes)["file_hashes"]


def test_plan_classifies_every_group(tmp_path):
    source, target = tmp_path / "a" / ".claude", tmp_path / "b" / ".claude"
    write_files(source, {"skills/same.md": "same", "skills/changed.md": "new", "skills/added.md": "add"})
    write_files(target, {"skills/same.md": "same", "skills/changed.md": "old", "skills/extra.md": "x"})
    contents = SnapshotContents.from_zip(snap.create_zip(["skills/"], source, 1, "m"))

    overlay = _planner(target.parent).plan(contents, target, ["skills/"], exact=False)
    assert overlay.to_create == ["skills/added.md"]
    assert overlay.to_overwrite == ["skills/changed.md"]
    assert overlay.unchanged == ["skills/same.md"]
    assert overlay.only_local == ["skills/extra.md"]
    assert overlay.to_delete == []

    exact = _planner(target.parent).plan(contents, target, ["skills/"], exact=True)
    assert exact.to_delete == ["skills/extra.md"]


def test_file_differing_only_by_home_path_is_unchanged(tmp_path):
    source, target = tmp_path / "home1" / ".claude", tmp_path / "home2" / ".claude"
    def settings_for(launcher, claude_folder):
        # json.dumps escapes the path, so a Windows backslash stays valid JSON.
        return json.dumps({"statusLine": {"command": f"{launcher} {claude_folder / 'statusline.py'}"}})

    write_files(source, {"settings.json": settings_for("python", source)})
    # The target spells its own home, a different launcher and compact JSON.
    target_settings = settings_for("python3", target)
    write_files(target, {"settings.json": target_settings})
    contents = SnapshotContents.from_zip(snap.create_zip(["settings.json"], source, 1, "m"))

    plan = _planner(target.parent).plan(contents, target, ["settings.json"], exact=False)
    assert plan.unchanged == ["settings.json"]
    assert not plan.has_changes


def test_windows_home_path_matches_posix_snapshot(tmp_path):
    source, target = tmp_path / "home1" / ".claude", tmp_path / "win" / ".claude"
    write_files(source, {"hooks.md": f"run {source}/hooks/guard.py"})
    write_files(target, {"hooks.md": r"run C:\Users\amit\.claude\hooks\guard.py"})
    contents = SnapshotContents.from_zip(snap.create_zip(["hooks.md"], source, 1, "m"))
    windows = _planner(PureWindowsPath(r"C:\Users\amit"), python="python", sep="\\")
    assert windows.plan(contents, target, ["hooks.md"], exact=False).unchanged == ["hooks.md"]


def test_unsafe_zip_member_is_refused():
    with pytest.raises(UnsafeSnapshotEntryError):
        SnapshotContents.from_zip(build_v3_zip({"../evil.txt": "x"}))
    with pytest.raises(ValueError):
        snap.check_member_name("/etc/passwd")


def test_pull_restores_v3_snapshot_and_computes_hashes(isolated_home):
    provider = MemoryProvider()
    store_raw_zip(provider, build_v3_zip({"CLAUDE.md": "# old", "skills/a.md": "a"}))
    write_files(claude_dir(), {"skills/local.md": "mine"})
    cfg = {"storage": "local", "tracked": ["CLAUDE.md", "skills/"]}

    prepared = core.prepare_pull(None, cfg, provider, exact=True)
    assert prepared.contents.tracked is None
    assert prepared.plan.tracked_roots == ["CLAUDE.md", "skills"]  # from the local config
    assert prepared.plan.to_delete == ["skills/local.md"]

    result = core.pull(None, cfg, provider)
    assert result["created"] == 2
    assert (claude_dir() / "CLAUDE.md").read_text() == "# old"
    state = json.loads((isolated_home / ".claude-cfg" / "state.json").read_text())
    assert state["file_hashes"]["CLAUDE.md"] == sha256_hex(b"# old")


def test_snapshot_excluded_member_is_never_written(isolated_home):
    provider = MemoryProvider()
    store_raw_zip(provider, build_v3_zip({".credentials.json": "{}", "CLAUDE.md": "x"}))
    core.pull(None, {"storage": "local", "tracked": ["CLAUDE.md"]}, provider)
    assert not (claude_dir() / ".credentials.json").exists()
    assert (claude_dir() / "CLAUDE.md").exists()
