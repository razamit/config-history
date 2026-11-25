"""`claude-cfg integrate install | remove | status`."""

import json

import pytest
from typer.testing import CliRunner

from claude_cfg.cfg_push_skill import SKILL_MARKER, SKILL_TEXT
from claude_cfg.cli import app, output
from claude_cfg.paths import claude_dir

runner = CliRunner()
OUR_ENTRY = {"type": "command", "command": "claude-cfg session-hook start", "timeout": 15}
END_ENTRY = {"type": "command", "command": "claude-cfg session-hook end", "timeout": 30}
LEGACY_ENTRY = {"type": "command", "command": "claude-cfg status --hook", "timeout": 10}
INSTALLED_HOOKS = {
    "SessionStart": [{"matcher": "startup", "hooks": [OUR_ENTRY]}],
    "SessionEnd": [{"hooks": [END_ENTRY]}],
}


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


def _settings_path():
    return claude_dir() / "settings.json"


def _skill_path():
    return claude_dir() / "skills" / "cfg-push" / "SKILL.md"


def _invoke(*args):
    return runner.invoke(app, ["integrate", *args])


def test_install_creates_settings_and_skill():
    result = _invoke("install")
    assert result.exit_code == 0, result.output
    settings = json.loads(_settings_path().read_text())
    assert settings == {"hooks": INSTALLED_HOOKS}
    skill = _skill_path().read_text()
    assert skill == SKILL_TEXT and SKILL_MARKER in skill
    for line in ("argument-hint: [message]", "disable-model-invocation: true",
                 "allowed-tools: Bash(claude-cfg push *)"):
        assert line in skill
    assert chr(0x2014) not in skill  # no em dash


def test_install_twice_adds_nothing_and_keeps_other_keys():
    other_hook = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hi"}]}
    original = {"model": "opus", "hooks": {"SessionStart": [other_hook], "Stop": [{"hooks": []}]}}
    _settings_path().parent.mkdir(parents=True)
    _settings_path().write_text(json.dumps(original))
    _invoke("install")
    once = _settings_path().read_text()
    second = _invoke("install")
    assert "already" in second.output
    assert _settings_path().read_text() == once
    settings = json.loads(once)
    assert settings["model"] == "opus" and settings["hooks"]["Stop"] == [{"hooks": []}]
    assert settings["hooks"]["SessionStart"][0] == other_hook
    assert len(settings["hooks"]["SessionStart"]) == 2


def test_remove_takes_out_only_our_entry_and_empty_containers():
    other_hook = {"matcher": "resume", "hooks": [{"type": "command", "command": "echo hi"}]}
    _settings_path().parent.mkdir(parents=True)
    _settings_path().write_text(json.dumps({"model": "opus", "hooks": {"SessionStart": [other_hook]}}))
    _invoke("install")
    assert _invoke("remove").exit_code == 0
    assert json.loads(_settings_path().read_text()) == {
        "model": "opus", "hooks": {"SessionStart": [other_hook]},
    }
    assert not _skill_path().exists() and not _skill_path().parent.exists()


def test_remove_cleans_up_hooks_object_it_emptied():
    _invoke("install")
    _invoke("remove")
    assert json.loads(_settings_path().read_text()) == {}


def test_shared_matcher_group_keeps_other_entries():
    shared = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hi"}, OUR_ENTRY]}
    _settings_path().parent.mkdir(parents=True)
    _settings_path().write_text(json.dumps({"hooks": {"SessionStart": [shared]}}))
    _invoke("remove")
    remaining = json.loads(_settings_path().read_text())["hooks"]["SessionStart"]
    assert remaining == [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo hi"}]}]


def test_invalid_json_is_refused_and_left_alone():
    _settings_path().parent.mkdir(parents=True)
    _settings_path().write_text("{not json")
    result = _invoke("install")
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
    assert _settings_path().read_text() == "{not json"
    assert not _skill_path().exists()
    assert list(_settings_path().parent.iterdir()) == [_settings_path()]


def test_foreign_skill_is_never_overwritten_or_removed():
    _skill_path().parent.mkdir(parents=True)
    _skill_path().write_text("my own skill")
    assert "not written by claude-cfg" in _invoke("install").output
    assert "not written by claude-cfg" in _invoke("remove").output
    assert _skill_path().read_text() == "my own skill"


def test_status_reports_both_parts():
    before = _invoke("status").output
    assert "SessionStart hook: not installed" in before and "/cfg-push skill: missing" in before
    _invoke("install")
    after = _invoke("status").output
    assert "SessionStart hook: installed" in after and "/cfg-push skill: installed" in after


def test_symlinked_settings_keeps_the_link(tmp_path):
    dotfiles = tmp_path / "dotfiles" / "settings.json"
    dotfiles.parent.mkdir()
    dotfiles.write_text(json.dumps({"model": "opus"}))
    _settings_path().parent.mkdir(parents=True)
    _settings_path().symlink_to(dotfiles)
    assert _invoke("install").exit_code == 0
    assert _settings_path().is_symlink()
    assert json.loads(dotfiles.read_text())["hooks"]["SessionStart"][0]["hooks"] == [OUR_ENTRY]


def _write_settings(settings: dict) -> None:
    _settings_path().parent.mkdir(parents=True, exist_ok=True)
    _settings_path().write_text(json.dumps(settings))


def test_install_replaces_the_old_status_hook_and_keeps_others():
    other_hook = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo hi"}]}
    legacy_group = {"matcher": "startup", "hooks": [LEGACY_ENTRY]}
    _write_settings({"hooks": {"SessionStart": [other_hook, legacy_group]}})
    status_before = _invoke("status").output
    assert "an older version" in status_before
    result = _invoke("install")
    assert result.exit_code == 0 and "Added the SessionStart hook" in result.output
    hooks = json.loads(_settings_path().read_text())["hooks"]
    assert hooks["SessionStart"] == [other_hook, {"matcher": "startup", "hooks": [OUR_ENTRY]}]
    assert hooks["SessionEnd"] == [{"hooks": [END_ENTRY]}]
    assert "status --hook" not in json.dumps(hooks)
    assert "an older version" not in _invoke("status").output


def test_install_adds_a_missing_end_hook():
    _write_settings({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [OUR_ENTRY]}]}})
    assert _invoke("install").exit_code == 0
    assert json.loads(_settings_path().read_text()) == {"hooks": INSTALLED_HOOKS}
    second = _invoke("install")
    assert "already" in second.output


def test_remove_takes_out_the_old_hook_too():
    _write_settings({"model": "opus", "hooks": {"SessionStart": [{"hooks": [LEGACY_ENTRY]}]}})
    assert _invoke("remove").exit_code == 0
    assert json.loads(_settings_path().read_text()) == {"model": "opus"}


def test_odd_session_end_shape_is_refused():
    _write_settings({"hooks": {"SessionEnd": {"not": "a list"}}})
    result = _invoke("install")
    assert result.exit_code == 1 and "SessionEnd" in result.output
    assert json.loads(_settings_path().read_text()) == {"hooks": {"SessionEnd": {"not": "a list"}}}
