"""CLAUDE_CONFIG_DIR: where the Claude folder and .claude.json live, and
tokens that round-trip when the Claude folder is not inside home."""

import json
from pathlib import PurePosixPath

from claude_cfg import core
from claude_cfg import paths as paths_mod
from claude_cfg import snapshot as snap
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.paths import claude_dir, claude_json_file, collapse_paths, expand_paths
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files


def test_unset_means_home_dot_claude(isolated_home):
    assert claude_dir() == isolated_home / ".claude"
    assert claude_json_file() == isolated_home / ".claude.json"


def test_absolute_value_moves_both_paths(isolated_home, tmp_path, monkeypatch):
    configured = tmp_path / "elsewhere" / "claude-config"
    monkeypatch.setenv(paths_mod.CLAUDE_CONFIG_DIR_ENV, str(configured))
    assert claude_dir() == configured
    assert claude_json_file() == configured / ".claude.json"
    assert paths_mod.detect_target().claude_home == configured


def test_relative_value_is_ignored(isolated_home, monkeypatch):
    monkeypatch.setenv(paths_mod.CLAUDE_CONFIG_DIR_ENV, "relative/dir")
    assert claude_dir() == isolated_home / ".claude"
    assert claude_json_file() == isolated_home / ".claude.json"


def test_tokens_round_trip_with_unrelated_claude_folder():
    home, claude_home = PurePosixPath("/home/bob"), PurePosixPath("/srv/cfg/claude")
    value = "python /srv/cfg/claude/hooks/a.py --log /home/bob/logs/x.txt"
    stored = collapse_paths(value, home, claude_home)
    assert stored == "python ${CLAUDE_HOME}/hooks/a.py --log ${HOME}/logs/x.txt"
    assert expand_paths(stored, home, "/", claude_home) == value


def test_claude_folder_inside_home_wins_over_home():
    home, claude_home = PurePosixPath("/home/bob"), PurePosixPath("/home/bob/.config/claude")
    stored = collapse_paths("/home/bob/.config/claude/x.py /home/bob/y", home, claude_home)
    assert stored == "${CLAUDE_HOME}/x.py ${HOME}/y"


def test_tilde_shortcut_is_not_the_claude_folder_when_moved():
    stored = collapse_paths("~/.claude/x.py", PurePosixPath("/home/bob"), PurePosixPath("/srv/claude"))
    assert stored == "~/.claude/x.py"


def test_snapshot_moves_between_default_and_configured_folders(isolated_home, tmp_path, monkeypatch):
    """A snapshot from a plain ~/.claude restores into a CLAUDE_CONFIG_DIR
    folder with each token pointing at the right place, and back again."""
    provider = MemoryProvider()
    cfg = {"storage": "local", "tracked": ["settings.json"]}
    settings = {"hooks": f"node {claude_dir()}/hooks/a.js", "log": f"{isolated_home}/logs/x"}
    write_files(claude_dir(), {"settings.json": json.dumps(settings), "hooks/a.js": "1"})
    core.push("plain", cfg, provider)

    configured = tmp_path / "moved-claude"
    monkeypatch.setenv(paths_mod.CLAUDE_CONFIG_DIR_ENV, str(configured))
    core.pull(None, cfg, provider)
    restored = json.loads((configured / "settings.json").read_text())
    assert restored == {"hooks": f"node {configured}/hooks/a.js", "log": f"{isolated_home}/logs/x"}

    core.push("moved", cfg, provider)
    monkeypatch.delenv(paths_mod.CLAUDE_CONFIG_DIR_ENV)
    (claude_dir() / "settings.json").write_text("{}")
    core.pull(None, cfg, provider)
    assert json.loads((claude_dir() / "settings.json").read_text()) == settings


def test_transform_defaults_keep_old_behavior(tmp_path):
    claude = tmp_path / ".claude"
    transform = PathTokenTransform.for_claude_dir(claude)
    assert transform.home == tmp_path and transform.claude_home == claude
    stored = transform.to_stored("s.json", json.dumps({"p": f"{claude}/x"}).encode())
    assert json.loads(stored) == {"p": "${CLAUDE_HOME}/x"}
