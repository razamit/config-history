"""Only an allowlist under plugins/ is captured, and volatile files never ask for a save.

Claude Code keeps each plugin's private data at plugins/data/<id>/ (the
config-history plugin keeps its virtual environment there) and rewrites
caches under plugins/ during a session. None of that may be captured,
planned for overwrite or planned for deletion.
"""

from pathlib import Path

import pytest

from claude_cfg import core
from claude_cfg.autosave_manager import AutoSaveOutcome
from claude_cfg.autosave_setup import build_autosave_manager, detect_local_changes
from claude_cfg.core import this_machine_transform
from claude_cfg.default_history import load_or_create_config
from claude_cfg.exclusion_filter import is_excluded, is_excluded_folder
from claude_cfg.paths import claude_dir
from claude_cfg.providers import get_provider
from claude_cfg.restore_plan import RestorePlanner
from claude_cfg.restore_writer import SafeDeleter
from claude_cfg.session_hook_lines import unsaved_changes_line
from claude_cfg.snapshot_contents import SnapshotContents
from claude_cfg.volatile_paths import is_volatile, without_volatile
from tests.sync_helpers import write_files

ALLOWLISTED = ["plugins/installed_plugins.json", "plugins/known_marketplaces.json"]
PLUGIN_DATA = "plugins/data/config-history-razamit"
MANAGED_FILES = {
    f"{PLUGIN_DATA}/venv-1/bin/python": "binary",
    f"{PLUGIN_DATA}/venv-1/lib/python3.12/site-packages/claude_cfg/__init__.py": "x",
    f"{PLUGIN_DATA}/install-marker.json": "{}",
    "plugins/plugin-directory-cache-v2.json": "{}",
    "plugins/plugin-catalog-cache.json": "{}",
    "plugins/blocklist.json": "[]",
    "plugins/store/entry.json": "{}",
}


@pytest.fixture
def default_cfg(isolated_home):
    files = {"settings.json": '{"a": 1}', ALLOWLISTED[0]: '{"plugins": {}}',
             ALLOWLISTED[1]: '{"lastUpdated": "1"}'}
    write_files(claude_dir(), {**files, **MANAGED_FILES})
    return load_or_create_config()


def _is_managed(path: str) -> bool:
    return path.startswith("plugins/") and path not in ALLOWLISTED


def test_only_allowlisted_plugin_files_pass_the_filter():
    for path in ALLOWLISTED + ["Plugins/Installed_Plugins.json"]:
        assert not is_excluded(path)
    for path in MANAGED_FILES:
        assert is_excluded(path)
    assert not is_excluded_folder("plugins")
    for folder in ("plugins/data", "plugins/store", "plugins/cache", PLUGIN_DATA):
        assert is_excluded_folder(folder)


def test_plugin_data_folder_is_never_captured(default_cfg):
    result = core.push("one", default_cfg, get_provider(default_cfg))
    prepared = core.prepare_pull(result["id"], default_cfg, get_provider(default_cfg))
    captured = set(prepared.contents.stored_files)
    assert set(ALLOWLISTED) <= captured
    assert not [path for path in captured if _is_managed(path)]


def test_restore_never_plans_to_overwrite_or_delete_plugin_data(default_cfg):
    provider = get_provider(default_cfg)
    saved = core.push("one", default_cfg, provider)
    write_files(claude_dir(), {f"{PLUGIN_DATA}/venv-1/bin/python": "changed",
                               f"{PLUGIN_DATA}/venv-2/new.py": "new", "plugins/store/b.json": "{}"})
    plan = core.prepare_pull(saved["id"], default_cfg, provider, exact=True).plan
    planned = plan.to_create + plan.to_overwrite + plan.to_delete + plan.only_local
    assert not [path for path in planned if _is_managed(path)]


def test_hostile_snapshot_member_inside_plugin_data_is_ignored(default_cfg):
    stored = {f"{PLUGIN_DATA}/venv-1/bin/python": b"evil", ALLOWLISTED[0]: b'{"plugins": {}}'}
    contents = SnapshotContents(manifest={}, stored_files=stored)
    planner = RestorePlanner(this_machine_transform(), case_probe=lambda folder: False)
    plan = planner.plan(contents, claude_dir(), ["plugins/"], exact=True)
    assert not [path for path in plan.files_to_write + plan.to_delete if _is_managed(path)]
    deleter = SafeDeleter(claude_dir(), plan.tracked_roots)
    assert not deleter.may_delete(f"{PLUGIN_DATA}/venv-1/bin/python")
    assert deleter.may_delete(ALLOWLISTED[0])


def test_volatile_paths():
    assert is_volatile("plugins/known_marketplaces.json")
    assert not is_volatile("plugins/installed_plugins.json")
    assert without_volatile(["a", "plugins/known_marketplaces.json", "b"]) == ["a", "b"]


def test_volatile_only_change_never_saves_or_notifies(default_cfg):
    assert build_autosave_manager(default_cfg).run().outcome is AutoSaveOutcome.SAVED
    write_files(claude_dir(), {ALLOWLISTED[1]: '{"lastUpdated": "2"}'})
    report = detect_local_changes(default_cfg)
    assert not report.needs_save and unsaved_changes_line(report) is None
    assert build_autosave_manager(default_cfg).run().outcome is AutoSaveOutcome.NO_CHANGES
    status = core.status(default_cfg)
    assert status.local_changes.modified == [ALLOWLISTED[1]], "status still lists it"


def test_volatile_path_is_saved_with_a_real_change_but_not_named(default_cfg):
    build_autosave_manager(default_cfg).run()
    write_files(claude_dir(), {ALLOWLISTED[1]: '{"lastUpdated": "3"}', "settings.json": '{"a": 2}'})
    result = build_autosave_manager(default_cfg).run()
    assert result.outcome is AutoSaveOutcome.SAVED
    assert result.changed_paths == ["settings.json"]
    prepared = core.prepare_pull(result.snapshot_id, default_cfg, get_provider(default_cfg))
    assert prepared.contents.stored_files[ALLOWLISTED[1]].endswith(b'"3"}')
    assert Path(claude_dir() / ALLOWLISTED[1]).is_file()
