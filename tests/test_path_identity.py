"""Case, Unicode and trailing-dot spellings of one path count as one file."""

import io
import json
import zipfile

import pytest

from claude_cfg import core, path_matching
from claude_cfg.exclusion_filter import is_excluded
from claude_cfg.path_identity import path_identity
from claude_cfg.paths import claude_dir
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import push_from_other_machine, read_tree, store_raw_zip, write_files

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/", "plugins/"]}


def hostile_zip(files: dict[str, str], tracked: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 4, "id": 1, "timestamp": "2026-01-01T00:00:00Z", "message": "x",
            "machine": "evil", "files": list(files), "tracked": tracked,
        }))
    return buffer.getvalue()


def test_identity_folds_case_unicode_and_trailing_dots():
    assert path_identity("Skills/Foo.MD") == path_identity("skills/foo.md")
    assert path_identity("café.md") == path_identity("café.md")
    assert path_identity("skills/foo. /a.md ") == path_identity("skills/foo/a.md")


@pytest.mark.parametrize("name", [
    ".Credentials.json", ".CREDENTIALS.JSON", ".credentials.json.", "Projects/p/chat.jsonl",
    "PROJECTS /x", "skills/.Git/config", "Plugins/Cache/x", ".claude.json",
    ".claude.json.backup.1712", ".Claude.json", "debug.LOG",
])
def test_exclusion_filter_ignores_spelling(name):
    assert is_excluded(name)


@pytest.fixture
def case_insensitive_target(monkeypatch):
    monkeypatch.setattr(path_matching, "folder_ignores_case", lambda folder: True)


def test_case_variant_on_disk_is_the_same_file_not_a_local_extra(tmp_path, case_insensitive_target):
    provider = MemoryProvider()
    source = tmp_path / "src" / ".claude"
    write_files(source, {"skills/foo/SKILL.md": "from snapshot"})
    push_from_other_machine(provider, source, ["skills/"], "one")
    write_files(claude_dir(), {"skills/Foo/SKILL.md": "local edit"})

    prepared = core.prepare_pull(None, CFG, provider, exact=True)
    assert prepared.plan.to_overwrite == ["skills/Foo/SKILL.md"]
    assert prepared.plan.to_delete == [] and prepared.plan.to_create == []

    result = core.pull(None, CFG, provider, exact=True, command_runner=None)
    assert result["deleted"] == 0
    tree = read_tree(claude_dir())
    assert tree == {"skills/Foo/SKILL.md": b"from snapshot"}


def test_case_variant_of_an_excluded_name_never_overwrites_it():
    provider = MemoryProvider()
    write_files(claude_dir(), {".credentials.json": "REAL LOGIN", "projects/p/chat.jsonl": "history"})
    store_raw_zip(provider, hostile_zip({".Credentials.json": "ATTACKER"}, ["Projects", "skills"]))
    prepared = core.prepare_pull(None, CFG, provider, exact=True)
    assert prepared.plan.files_to_write == [] and prepared.plan.to_delete == []
    core.pull(None, CFG, provider, exact=True)
    assert (claude_dir() / ".credentials.json").read_text() == "REAL LOGIN"
    assert (claude_dir() / "projects/p/chat.jsonl").read_text() == "history"


def test_two_members_differing_only_in_case_write_one_file(case_insensitive_target):
    provider = MemoryProvider()
    store_raw_zip(provider, hostile_zip({"skills/A.md": "upper", "skills/a.md": "lower"}, ["skills"]))
    prepared = core.prepare_pull(None, CFG, provider)
    assert prepared.plan.to_create == ["skills/A.md"]
    assert "differs only in case" in prepared.plan.left_untouched["skills/a.md"]
