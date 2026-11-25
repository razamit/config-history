"""Exact names win; case folding applies only on a case-insensitive target."""

import os

import pytest

from claude_cfg import core, path_matching, target_folder
from claude_cfg.path_matching import PathMatcher, folder_ignores_case, simple_case_fold
from claude_cfg.paths import claude_dir
from claude_cfg.sync_status import compare_hashes
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import store_raw_zip
from tests.test_path_identity import hostile_zip

CFG = {"storage": "local", "tracked": ["CLAUDE.md", "skills/", "plugins/"]}
LOOKALIKES = {
    "skills/Readme.md": "A", "skills/README.md": "B", "skills/straße.md": "C",
    "skills/strasse.md": "D", "skills/notes.md.": "E", "skills/notes.md": "F",
}
# Windows ignores a trailing dot, so there "notes.md." and "notes.md" are one
# file whatever the case rule: only "notes.md" is restored.
DOT_TWIN_LEFT_ON_WINDOWS = ["skills/notes.md."] if os.name == "nt" else []


@pytest.fixture
def force_case(monkeypatch):
    def force(ignores_case: bool) -> None:
        monkeypatch.setattr(path_matching, "folder_ignores_case", lambda folder: ignores_case)
    return force


def test_simple_fold_keeps_sharp_s_apart_from_ss():
    assert simple_case_fold("STRASSE") == "strasse"
    assert simple_case_fold("straße") == "straße"
    assert simple_case_fold("STRAẞE") == "straße"


def test_trailing_dots_matter_except_on_windows():
    assert PathMatcher(True, strips_trailing_dots=False).key("a/notes.md.") != "a/notes.md"
    assert PathMatcher(True, strips_trailing_dots=True).key("a/Notes.md. ") == "a/notes.md"
    assert PathMatcher(False, strips_trailing_dots=False).key("a/Foo.md") == "a/Foo.md"


def test_probe_answers_for_this_disk_and_cleans_up(tmp_path):
    answer = folder_ignores_case(tmp_path)
    (tmp_path / "x").write_text("x")
    assert answer == (tmp_path / "X").exists()
    assert sorted(os.listdir(tmp_path)) == ["x"]
    assert folder_ignores_case(tmp_path / "missing" / "deeper") == answer
    assert not (tmp_path / "missing").exists()


def _inspector_over(tmp_path, monkeypatch, names, ignores_case):
    (tmp_path / "skills").mkdir()
    real_listdir = os.listdir
    monkeypatch.setattr(
        target_folder.os, "listdir",
        lambda folder: names if str(folder).endswith("skills") else real_listdir(folder),
    )
    return target_folder.TargetFolderInspector(tmp_path, PathMatcher(ignores_case, False))


def test_exact_name_wins_when_both_case_variants_exist(tmp_path, monkeypatch):
    inspector = _inspector_over(tmp_path, monkeypatch, ["Foo.md", "foo.md"], ignores_case=False)
    assert inspector.on_disk_spelling("skills/foo.md") == "skills/foo.md"
    assert inspector.on_disk_spelling("skills/Foo.md") == "skills/Foo.md"


def test_case_variant_is_not_reused_on_a_case_sensitive_disk(tmp_path, monkeypatch):
    inspector = _inspector_over(tmp_path, monkeypatch, ["Foo.md"], ignores_case=False)
    assert inspector.on_disk_spelling("skills/foo.md") == "skills/foo.md"


def test_case_variant_is_reused_on_a_case_insensitive_disk(tmp_path, monkeypatch):
    inspector = _inspector_over(tmp_path, monkeypatch, ["Foo.md"], ignores_case=True)
    assert inspector.on_disk_spelling("skills/foo.md") == "skills/Foo.md"


def test_case_sensitive_target_restores_every_lookalike(force_case):
    force_case(False)
    provider = MemoryProvider()
    store_raw_zip(provider, hostile_zip(LOOKALIKES, ["skills"]))
    plan = core.prepare_pull(None, CFG, provider).plan
    assert sorted(plan.to_create) == sorted(set(LOOKALIKES) - set(DOT_TWIN_LEFT_ON_WINDOWS))
    assert list(plan.left_untouched) == DOT_TWIN_LEFT_ON_WINDOWS


def test_case_insensitive_target_folds_case_only(force_case):
    force_case(True)
    provider = MemoryProvider()
    store_raw_zip(provider, hostile_zip(LOOKALIKES, ["skills"]))
    plan = core.prepare_pull(None, CFG, provider).plan
    assert list(plan.left_untouched) == ["skills/Readme.md"] + DOT_TWIN_LEFT_ON_WINDOWS
    assert "skills/straße.md" in plan.to_create and "skills/strasse.md" in plan.to_create
    assert "skills/notes.md" in plan.to_create
    assert ("skills/notes.md." in plan.to_create) == (os.name != "nt")


def test_case_insensitive_target_prefers_the_member_spelled_like_the_disk(force_case):
    force_case(True)
    (claude_dir() / "skills").mkdir(parents=True)
    (claude_dir() / "skills/b.md").write_text("old")
    provider = MemoryProvider()
    store_raw_zip(provider, hostile_zip({"skills/B.md": "upper", "skills/b.md": "lower"}, ["skills"]))
    plan = core.prepare_pull(None, CFG, provider).plan
    assert plan.to_overwrite == ["skills/b.md"]
    assert plan.content_to_write["skills/b.md"] == b"lower"
    assert list(plan.left_untouched) == ["skills/B.md"]


def test_status_matches_exact_names_before_folding():
    recorded = {"a/Foo.md": "1", "a/foo.md": "2"}
    changes = compare_hashes(recorded, {"a/Foo.md": "1", "a/foo.md": "CHANGED"}, lambda: True)
    assert changes.modified == ["a/foo.md"] and not changes.added and not changes.removed


def test_status_folds_leftovers_only_on_a_case_insensitive_disk():
    recorded, current = {"skills/foo.md": "1"}, {"skills/Foo.md": "1"}
    assert not compare_hashes(recorded, current, lambda: True).has_changes
    sensitive = compare_hashes(recorded, current, lambda: False)
    assert sensitive.added == ["skills/Foo.md"] and sensitive.removed == ["skills/foo.md"]
    changed = compare_hashes(recorded, {"skills/Foo.md": "2"}, lambda: True)
    assert changed.modified == ["skills/Foo.md"]
