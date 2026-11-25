"""``restore --only``: some files of a version, with its own backup and undo,
and the sync state left alone."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import snapshot as snap
from claude_cfg.backup_manager import BackupManager, BackupManifest, BackupRecord
from claude_cfg.cli import app, output
from claude_cfg.content_hashing import sha256_hex
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.default_history import load_or_create_config
from claude_cfg.errors import RestoreSelectionError
from claude_cfg.path_matching import PathMatcher
from claude_cfg.paths import backups_dir, claude_dir, state_file
from claude_cfg.pull_manager import prepare_pull
from claude_cfg.restore_plan import RestorePlanner
from claude_cfg.restore_selection import RestoreSelection
from claude_cfg.snapshot_store import SnapshotStore
from claude_cfg.undo_manager import UndoManager
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import read_tree, write_files

runner = CliRunner()
FIRST = {"settings.json": '{"a": 1}', "CLAUDE.md": "# one",
         "skills/demo/SKILL.md": "demo one", "skills/demo/notes.md": "notes one",
         "skills/other/SKILL.md": "other one"}
SECOND = {"settings.json": '{"a": 2}', "CLAUDE.md": "# two",
          "skills/demo/SKILL.md": "demo two", "skills/demo/notes.md": "notes two",
          "skills/other/SKILL.md": "other two"}


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def two_versions(isolated_home):
    """Version 1 and version 2 saved; the files on disk match version 2."""
    write_files(claude_dir(), FIRST)
    load_or_create_config()
    invoke("save", "first")
    write_files(claude_dir(), SECOND)
    invoke("save", "second")
    return claude_dir()


def invoke(*args, expected_exit=0):
    result = runner.invoke(app, list(args))
    assert result.exit_code == expected_exit, result.output
    return result.output


def text_of(relative_path: str) -> str:
    return (claude_dir() / relative_path).read_text()


def test_only_one_file(two_versions):
    preview = invoke("restore", "--point", "1", "--only", "settings.json", "--dry-run")
    assert "Only: settings.json" in preview and "~ settings.json" in preview
    assert "CLAUDE.md" not in preview and "Kept" not in preview
    assert 'Version 1, saved just now (' in preview and '"first" (saved by you)' in preview
    restored = invoke("restore", "--point", "1", "--only", "settings.json")
    assert "1 overwritten" in restored and "Only: settings.json" in restored
    assert 'What changed: "first" (saved by you)' in restored
    assert "not marked as matching it" in restored
    assert text_of("settings.json") == '{"a": 1}'
    assert text_of("CLAUDE.md") == "# two"


@pytest.mark.parametrize("folder", ["skills/demo/", "skills/demo", "./skills/demo/"])
def test_only_a_folder_prefix(two_versions, folder):
    invoke("restore", "--point", "1", "--only", folder)
    assert text_of("skills/demo/SKILL.md") == "demo one"
    assert text_of("skills/demo/notes.md") == "notes one"
    assert text_of("skills/other/SKILL.md") == "other two"
    assert text_of("settings.json") == '{"a": 2}'


def test_only_repeated(two_versions):
    invoke("restore", "--point", "1", "--only", "settings.json", "--only", "skills/other/")
    assert text_of("settings.json") == '{"a": 1}'
    assert text_of("skills/other/SKILL.md") == "other one"
    assert text_of("CLAUDE.md") == "# two"


def test_a_partial_restore_that_changes_nothing_says_nothing_about_the_next_save(two_versions):
    restored = invoke("restore", "--point", "2", "--only", "settings.json")
    assert "0 overwritten" in restored and "Only: settings.json" in restored
    assert "Nothing changed, so no backup was made." in restored
    assert "records the mix" not in restored and "not marked as matching" not in restored


def test_backup_and_undo_cover_only_the_chosen_files(two_versions):
    state_before = state_file().read_bytes()
    invoke("restore", "--point", "1", "--only", "settings.json")
    [backup] = BackupManager(backups_dir()).list_backups()
    assert backup.manifest.overwritten == ["settings.json"]
    assert backup.manifest.only_paths == ["settings.json"]
    assert read_tree(backup.files_dir) == {"settings.json": b'{"a": 2}'}
    assert state_file().read_bytes() == state_before, "a partial restore leaves the state"
    undone = invoke("undo")
    assert "1 file(s) put back" in undone and "sync state was left" not in undone
    assert text_of("settings.json") == '{"a": 2}'
    assert state_file().read_bytes() == state_before


def test_next_automatic_save_records_the_mixed_state(two_versions):
    invoke("restore", "--point", "1", "--only", "settings.json")
    saved = invoke("autosave")
    assert saved.startswith("Saved version 3 (1 file changed: settings.json).")
    assert "settings.json changed" in invoke("history")
    assert "Local changes: none." in invoke("status")


def test_no_match_lists_near_matches_and_writes_nothing(two_versions):
    before = read_tree(claude_dir())
    refused = invoke("restore", "--point", "1", "--only", "setings.json", expected_exit=1)
    assert "'setings.json' matches no file or folder" in refused
    assert "Did you mean: settings.json?" in refused
    folder = invoke("restore", "--point", "1", "--only", "skills/dmeo/", expected_exit=1)
    assert "skills/demo/" in folder
    assert read_tree(claude_dir()) == before
    assert BackupManager(backups_dir()).list_backups() == []


@pytest.mark.parametrize("value", ["../settings.json", "skills/../../x", "/etc/passwd", "C:/x", ".."])
def test_unsafe_paths_are_refused(two_versions, value):
    before = read_tree(claude_dir())
    refused = invoke("restore", "--point", "1", "--only", value, expected_exit=1)
    assert "is not a path inside the version" in refused
    assert read_tree(claude_dir()) == before


def test_only_with_exact_is_refused(two_versions):
    refused = invoke("restore", "--point", "1", "--only", "settings.json", "--exact", "--yes",
                     expected_exit=1)
    assert "cannot be used together" in refused
    assert text_of("settings.json") == '{"a": 2}'


def test_external_members_are_never_selected():
    matcher = PathMatcher(ignores_case=False)
    names = ["settings.json", "_external/mcp-servers.json"]
    with pytest.raises(RestoreSelectionError):
        RestoreSelection.from_values(["_external/"]).pick(names, matcher)
    assert RestoreSelection.from_values(["settings.json"]).pick(names, matcher) == {"settings.json"}


def test_case_matching_follows_the_disk():
    selection = RestoreSelection.from_values(["Skills/Demo/"])
    names = ["skills/demo/SKILL.md", "skills/demolition.md"]
    assert selection.pick(names, PathMatcher(ignores_case=True)) == {"skills/demo/SKILL.md"}
    with pytest.raises(RestoreSelectionError):
        selection.pick(names, PathMatcher(ignores_case=False))


def test_a_partial_pull_never_plans_mcp_servers(isolated_home, tmp_path):
    source = tmp_path / "source"
    write_files(source, {"settings.json": "{}"})
    provider = MemoryProvider()
    SnapshotStore(provider).store_zip(
        lambda snapshot_id: snap.create_zip(["settings.json"], source, snapshot_id, "one")
    )

    def mcp_planner(contents, exact):
        raise AssertionError("a partial pull must not plan MCP servers")

    prepared = prepare_pull(
        SnapshotStore(provider), RestorePlanner(PathTokenTransform.for_claude_dir(source, tmp_path)),
        tmp_path / "target", ["settings.json"], mcp_planner=mcp_planner,
        selection=RestoreSelection.from_values(["settings.json"]),
    )
    assert prepared.mcp_plan is None and prepared.plan.to_create == ["settings.json"]


class RefusingStateStore:
    def load(self):
        raise AssertionError("undo of a partial pull must not read the sync state")

    def restore(self, saved):
        raise AssertionError("undo of a partial pull must not rewind the sync state")


def test_undo_of_a_partial_pull_never_touches_the_state(tmp_path):
    target = tmp_path / "claude"
    write_files(target, {"settings.json": "new"})
    backups = BackupManager(tmp_path / "backups")
    folder = tmp_path / "backups" / "20261125T120000Z"
    write_files(folder / "files", {"settings.json": "old"})
    manifest = BackupManifest(
        snapshot_key="k", snapshot_id=1, created_at="2026-11-25T12:00:00Z",
        tracked_roots=["settings.json"], overwritten=["settings.json"], deleted=[], created=[],
        written_hashes={"settings.json": sha256_hex(b"new")}, previous_state={"snapshot_key": "k"},
        target_dir=str(target.resolve()), only_paths=["settings.json"],
    )
    backups.save_manifest(BackupRecord(folder, manifest))
    result = UndoManager(backups, target, RefusingStateStore()).undo()
    assert result.partial and not result.state_restored
    assert (target / "settings.json").read_text() == "old"


@pytest.fixture
def versions_with_a_dash_member(isolated_home):
    """Like ``two_versions``, but both versions also hold a top-level file
    named ``--dry-run``, so ``--only --dry-run`` would match a member."""
    cfg = load_or_create_config()
    cfg["tracked"] = list(cfg["tracked"]) + ["--dry-run"]
    cfg_mod.save(cfg)
    write_files(claude_dir(), dict(FIRST, **{"--dry-run": "dash one"}))
    invoke("save", "first")
    write_files(claude_dir(), dict(SECOND, **{"--dry-run": "dash two"}))
    invoke("save", "second")
    return claude_dir()


def test_only_never_swallows_the_dry_run_flag(versions_with_a_dash_member):
    before = read_tree(claude_dir())
    refused = invoke("restore", "--point", "1", "--only", "settings.json", "--only", "--dry-run",
                     expected_exit=1)
    assert "--only needs a path after it, but got '--dry-run', which looks like an option" in refused
    assert "Nothing was restored" in refused
    assert read_tree(claude_dir()) == before
    assert BackupManager(backups_dir()).list_backups() == []


def test_a_member_starting_with_a_dash_is_named_with_dot_slash(versions_with_a_dash_member):
    preview = invoke("restore", "--dry-run", "--point", "1", "--only", "./--dry-run")
    assert "~ --dry-run" in preview and "Dry run: nothing was written." in preview
    assert text_of("--dry-run") == "dash two"


@pytest.mark.parametrize("value", ["-x", "--exact", " --dry-run", "-"])
def test_option_looking_values_are_refused(value):
    with pytest.raises(RestoreSelectionError, match="looks like an option"):
        RestoreSelection.from_values(["settings.json", value])


def test_dry_run_flag_may_come_first(two_versions):
    before = read_tree(claude_dir())
    preview = invoke("restore", "--dry-run", "--point", "1", "--only", "settings.json")
    assert "Only: settings.json" in preview and "Dry run: nothing was written." in preview
    assert read_tree(claude_dir()) == before


def test_undo_removes_a_file_the_partial_restore_created(two_versions):
    """A file only the version has is created by ``--only`` and removed by undo."""
    (claude_dir() / "skills/demo/notes.md").unlink()
    invoke("save", "without notes")
    (claude_dir() / "skills/other/SKILL.md").write_text("other edited")
    restored = invoke("restore", "--point", "2", "--only", "skills/demo/notes.md")
    assert "1 created" in restored
    assert text_of("skills/demo/notes.md") == "notes two"
    before_undo = read_tree(claude_dir())
    undone = invoke("undo")
    assert "1 removed" in undone
    assert not (claude_dir() / "skills/demo/notes.md").exists()
    after_undo = read_tree(claude_dir())
    del before_undo["skills/demo/notes.md"]
    assert after_undo == before_undo, "everything else is left as it was"
    assert text_of("skills/other/SKILL.md") == "other edited"


def test_folder_matches_whole_path_segments_only(isolated_home):
    write_files(claude_dir(), {"skills/demo/SKILL.md": "demo one",
                               "skills/demo-old/SKILL.md": "old one",
                               "skills/demo.md": "file one"})
    load_or_create_config()
    invoke("save", "first")
    write_files(claude_dir(), {"skills/demo/SKILL.md": "demo two",
                               "skills/demo-old/SKILL.md": "old two",
                               "skills/demo.md": "file two"})
    invoke("restore", "--point", "1", "--only", "skills/demo")
    assert text_of("skills/demo/SKILL.md") == "demo one"
    assert text_of("skills/demo-old/SKILL.md") == "old two"
    assert text_of("skills/demo.md") == "file two"


def test_help_names_the_option():
    assert "--only" in runner.invoke(app, ["restore", "--help"]).output
