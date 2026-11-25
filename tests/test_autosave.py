"""Auto-save: saving only on change, retention, the lock and the commands."""

import os
import time
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.autosave_manager import AutoSaveOutcome
from claude_cfg.autosave_message import MESSAGE_LIMIT, autosave_message, file_list_text
from claude_cfg.autosave_setup import build_autosave_manager
from claude_cfg.cli import app
from claude_cfg.config import is_autosave_enabled
from claude_cfg.default_history import load_or_create_config
from claude_cfg.exclusive_lock import ExclusiveFileLock
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.paths import autosave_lock_file, claude_dir
from claude_cfg.providers import get_provider
from claude_cfg.snapshot import read_manifest
from claude_cfg.snapshot_index import SnapshotIndexManager
from claude_cfg.snapshot_store import SnapshotStore
from tests.sync_helpers import write_files

runner = CliRunner()


@pytest.fixture
def default_cfg(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"a": 1}', "CLAUDE.md": "# rules"})
    return load_or_create_config()


def _run(cfg):
    return build_autosave_manager(cfg).run()


def _entries(cfg):
    return SnapshotStore(get_provider(cfg)).list_entries()


def test_first_run_saves_a_first_version(default_cfg):
    result = _run(default_cfg)
    assert result.outcome is AutoSaveOutcome.SAVED and result.first_version
    assert result.snapshot_id == 1 and result.previous_id is None
    (entry,) = _entries(default_cfg)
    assert entry.automatic and entry.message == "auto: first version"
    manifest = read_manifest(SnapshotStore(get_provider(default_cfg)).fetch_zip(entry))
    assert manifest["automatic"] is True


def test_changes_are_saved_with_a_generated_message(default_cfg):
    _run(default_cfg)
    write_files(claude_dir(), {"settings.json": '{"a": 2}', "skills/demo/SKILL.md": "demo"})
    result = _run(default_cfg)
    assert result.outcome is AutoSaveOutcome.SAVED
    assert result.snapshot_id == 2 and result.previous_id == 1
    assert result.changed_paths == ["settings.json", "skills/demo/SKILL.md"]
    assert _entries(default_cfg)[-1].message == (
        "auto: 2 files changed (settings.json, skills/demo/SKILL.md)"
    )


def test_no_changes_saves_nothing(default_cfg):
    _run(default_cfg)
    assert _run(default_cfg).outcome is AutoSaveOutcome.NO_CHANGES
    assert len(_entries(default_cfg)) == 1


def test_empty_claude_folder_saves_nothing(isolated_home):
    cfg = load_or_create_config()
    assert _run(cfg).outcome is AutoSaveOutcome.NO_CHANGES


def test_encryption_without_passphrase_skips_and_never_prompts(default_cfg, monkeypatch):
    default_cfg["encryption"] = {"enabled": True}
    monkeypatch.setattr("claude_cfg.passphrase._stdin_is_tty", lambda: True)
    monkeypatch.setattr("claude_cfg.passphrase._prompt_with_getpass", _fail_if_prompted)
    result = _run(default_cfg)
    assert result.outcome is AutoSaveOutcome.NO_PASSPHRASE
    assert _entries(default_cfg) == []


def test_encryption_with_env_passphrase_saves_encrypted(default_cfg, monkeypatch):
    default_cfg["encryption"] = {"enabled": True}
    monkeypatch.setenv(PASSPHRASE_ENV_VAR, "pw")
    result = _run(default_cfg)
    assert result.outcome is AutoSaveOutcome.SAVED
    assert _entries(default_cfg)[0].encrypted


def _fail_if_prompted():
    raise AssertionError("auto-save prompted for a passphrase")


def test_configured_backend_has_autosave_off_by_default(isolated_home):
    chosen = {"storage": "local", "local": {"path": str(isolated_home / "store")}, "tracked": []}
    assert not is_autosave_enabled(chosen)
    cfg_mod.set_autosave_enabled(chosen, True)
    assert is_autosave_enabled(chosen)


def test_retention_deletes_only_the_oldest_automatic_versions(default_cfg):
    default_cfg["autosave"]["keep"] = 2
    provider = get_provider(default_cfg)
    core.push("by hand", default_cfg, provider)  # 1, manual
    for number in range(4):  # 2..5, automatic
        write_files(claude_dir(), {"CLAUDE.md": f"# version {number}"})
        result = _run(default_cfg)
    assert result.pruned_count == 1
    remaining = _entries(default_cfg)
    assert [e.snapshot_id for e in remaining] == [1, 4, 5]
    assert not remaining[0].automatic and remaining[0].message == "by hand"


def test_retention_keeps_a_snapshot_whose_manifest_is_not_automatic(default_cfg):
    default_cfg["autosave"]["keep"] = 1
    provider = get_provider(default_cfg)
    core.push("by hand", default_cfg, provider)
    store = SnapshotStore(provider)
    forged = [replace(entry, automatic=True) for entry in store.list_entries()]
    SnapshotIndexManager(provider).save_cache(forged)  # the cache lies about #1
    write_files(claude_dir(), {"CLAUDE.md": "# changed"})
    assert _run(default_cfg).outcome is AutoSaveOutcome.SAVED
    assert [e.snapshot_id for e in _entries(default_cfg)] == [1, 2]


def test_held_lock_skips_quietly(default_cfg):
    holder = ExclusiveFileLock(autosave_lock_file())
    assert holder.try_acquire()
    try:
        assert _run(default_cfg).outcome is AutoSaveOutcome.LOCKED
        assert _entries(default_cfg) == []
    finally:
        holder.release()
    assert _run(default_cfg).outcome is AutoSaveOutcome.SAVED
    assert not autosave_lock_file().exists()


def test_stale_lock_is_replaced(default_cfg):
    lock_path = autosave_lock_file()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("12345\n")
    old = time.time() - 600
    os.utime(lock_path, (old, old))
    assert _run(default_cfg).outcome is AutoSaveOutcome.SAVED


def test_second_lock_cannot_be_taken_while_the_first_is_held(tmp_path):
    first, second = ExclusiveFileLock(tmp_path / "x.lock"), ExclusiveFileLock(tmp_path / "x.lock")
    assert first.try_acquire() and not second.try_acquire()
    first.release()
    assert second.try_acquire()


def test_failure_is_reported_not_raised(default_cfg):
    def broken(_cfg):
        raise ConnectionError("backend down")

    result = build_autosave_manager(default_cfg, provider_factory=broken).run()
    assert result.outcome is AutoSaveOutcome.FAILED and "backend down" in result.reason
    assert not autosave_lock_file().exists()


def test_message_is_capped():
    paths = [f"skills/skill-number-{n}/SKILL.md" for n in range(30)]
    message = autosave_message(paths, first_version=False)
    assert message.startswith("auto: 30 files changed (skills/skill-number-0/SKILL.md")
    assert message.endswith("more)") and len(message) <= MESSAGE_LIMIT + 10
    assert file_list_text(["a"]) == "a"
    assert autosave_message(["CLAUDE.md"], False) == "auto: 1 file changed (CLAUDE.md)"


def test_autosave_command_prints_one_line(default_cfg):
    first = runner.invoke(app, ["autosave"])
    assert first.exit_code == 0
    assert first.output == "Saved version 1, the first version of your settings.\n"
    write_files(claude_dir(), {"CLAUDE.md": "# new"})
    second = runner.invoke(app, ["autosave"])
    assert second.output.count("\n") == 1
    assert "Saved version 2 (1 file changed: CLAUDE.md)." in second.output
    assert "claude-cfg restore --point 1" in second.output
    assert runner.invoke(app, ["autosave"]).output.startswith("Nothing changed")


def test_config_autosave_toggles_and_sets_keep(default_cfg):
    off = runner.invoke(app, ["config", "autosave", "--disable"])
    assert off.exit_code == 0 and "Auto-save is off" in off.output
    assert cfg_mod.load()["autosave"]["enabled"] is False
    on = runner.invoke(app, ["config", "autosave", "--enable", "--keep", "7"])
    assert "Auto-save is on" in on.output and "newest 7" in on.output
    assert cfg_mod.load()["autosave"] == {"enabled": True, "keep": 7}
    assert "Auto-save is on" in runner.invoke(app, ["config", "autosave"]).output
