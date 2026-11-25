"""The sync state file and the status check."""

import json
import os
import platform

import pytest

from claude_cfg import core
from claude_cfg.paths import claude_dir, state_file
from claude_cfg.sync_status import SuggestedAction
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "settings.json", "skills/"]}


class FailingProvider(MemoryProvider):
    def list_keys(self, prefix: str = "") -> list[str]:
        raise ConnectionError("backend unreachable")


@pytest.fixture
def provider():
    provider = MemoryProvider()
    statusline = f"python {claude_dir()}/statusline.py"
    write_files(claude_dir(), {
        "CLAUDE.md": "# one",
        "settings.json": json.dumps({"statusLine": {"command": statusline}}),
        "statusline.py": "print('hi')",
        "skills/a.md": "a",
    })
    return provider


def _status(provider):
    return core.status(CFG, provider_factory=lambda: provider)


def _other_machine_pushes(provider, tmp_path):
    other = tmp_path / "other" / ".claude"
    write_files(other, {"CLAUDE.md": "# from the laptop"})
    return push_from_other_machine(provider, other, ["CLAUDE.md"], "laptop")


def test_push_writes_owner_only_state(provider):
    result = core.push("one", CFG, provider)
    state = json.loads(state_file().read_text())
    assert state["snapshot_key"] == result["key"] and state["action"] == "push"
    assert set(state["file_hashes"]) == {"CLAUDE.md", "settings.json", "skills/a.md", "statusline.py"}
    assert state["content_hash"] and state["synced_at"] and state["machine"]
    if platform.system() != "Windows":
        assert oct(os.stat(state_file()).st_mode & 0o777) == "0o600"


def test_pull_writes_state(provider, tmp_path):
    core.push("one", CFG, provider)
    entry = _other_machine_pushes(provider, tmp_path)
    core.pull(None, CFG, provider)
    state = json.loads(state_file().read_text())
    assert state["snapshot_key"] == entry.key and state["action"] == "pull"
    assert list(state["file_hashes"]) == ["CLAUDE.md"]


def test_status_clean_after_push(provider):
    core.push("one", CFG, provider)
    status = _status(provider)
    assert status.last_synced.snapshot_id == 1
    assert not status.local_changes.has_changes
    assert status.remote.latest.snapshot_id == 1 and not status.remote.is_newer
    assert status.suggested_action is SuggestedAction.NONE


def test_status_clean_after_pull_with_tokens(provider):
    core.push("one", CFG, provider)
    core.pull(1, CFG, provider, exact=True)
    assert not _status(provider).local_changes.has_changes


def test_status_reports_local_changes(provider):
    core.push("one", CFG, provider)
    write_files(claude_dir(), {"CLAUDE.md": "# edited", "skills/new.md": "n"})
    (claude_dir() / "skills/a.md").unlink()
    status = core.status(CFG)  # no provider: local only, no network
    assert status.local_changes.added == ["skills/new.md"]
    assert status.local_changes.modified == ["CLAUDE.md"]
    assert status.local_changes.removed == ["skills/a.md"]
    assert not status.remote.checked
    assert status.suggested_action is SuggestedAction.PUSH


def test_status_remote_newer(provider, tmp_path):
    core.push("one", CFG, provider)
    _other_machine_pushes(provider, tmp_path)
    status = _status(provider)
    assert status.remote.is_newer and status.remote.latest.snapshot_id == 2
    assert status.suggested_action is SuggestedAction.PULL


def test_status_both_sides_changed(provider, tmp_path):
    core.push("one", CFG, provider)
    _other_machine_pushes(provider, tmp_path)
    write_files(claude_dir(), {"CLAUDE.md": "# edited"})
    assert _status(provider).suggested_action is SuggestedAction.REVIEW


def test_status_without_state(provider, tmp_path):
    status = _status(provider)
    assert status.last_synced is None and status.local_changes is None
    assert status.suggested_action is SuggestedAction.PUSH  # empty backend

    _other_machine_pushes(provider, tmp_path)
    status = _status(provider)
    assert status.remote.is_newer
    assert status.suggested_action is SuggestedAction.PULL


def test_status_reports_remote_failure_instead_of_raising(provider):
    core.push("one", CFG, provider)
    write_files(claude_dir(), {"CLAUDE.md": "# edited"})
    status = core.status(CFG, provider_factory=FailingProvider)
    assert status.remote.error == "backend unreachable"
    assert status.local_changes.modified == ["CLAUDE.md"]
    assert status.suggested_action is SuggestedAction.PUSH


def test_status_reports_a_provider_that_cannot_be_built(provider):
    def broken_factory():
        raise ImportError("boto3 is not installed")

    status = core.status(CFG, provider_factory=broken_factory)
    assert status.remote.error == "boto3 is not installed"
    assert status.suggested_action is SuggestedAction.NONE


def test_corrupt_state_counts_as_no_state(provider):
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text("{not json")
    assert core.status(CFG).last_synced is None
