"""CLI tests for pull --dry-run / --exact, diff, undo and status."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app, output, restore_commands
from claude_cfg.paths import backups_dir, claude_dir, state_file
from tests.sync_helpers import read_tree, write_files

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def pushed(isolated_home):
    """Snapshot #1 is on a local backend; ~/.claude then gains an extra skill."""
    write_files(claude_dir(), {"CLAUDE.md": "# one", "skills/a.md": "a"})
    cfg = {
        "storage": "local",
        "tracked": ["CLAUDE.md", "skills/"],
        "local": {"path": str(isolated_home / "store")},
    }
    cfg_mod.save(cfg)
    assert runner.invoke(app, ["push", "one"]).exit_code == 0
    write_files(claude_dir(), {"skills/extra.md": "x", "CLAUDE.md": "# edited"})
    return isolated_home


def _invoke(*args, stdin=None):
    return runner.invoke(app, list(args), input=stdin)


def test_dry_run_writes_nothing_at_all(pushed):
    before = read_tree(pushed)
    result = _invoke("pull", "--dry-run", "--exact")
    assert result.exit_code == 0, result.output
    assert "Overwrite (1)" in result.output and "Delete (1)" in result.output
    assert "skills/extra.md" in result.output
    assert "nothing was written" in result.output
    assert read_tree(pushed) == before
    assert not backups_dir().exists()


def test_exact_pull_without_terminal_or_yes_refuses(pushed):
    result = _invoke("pull", "--exact")
    assert result.exit_code == 1
    assert "--yes" in result.output and "would delete 1 file" in result.output
    assert (claude_dir() / "skills/extra.md").exists()
    assert (claude_dir() / "CLAUDE.md").read_text() == "# edited"


def test_exact_pull_with_yes_deletes(pushed):
    result = _invoke("pull", "--exact", "--yes")
    assert result.exit_code == 0, result.output
    assert "1 deleted" in result.output and "claude-cfg undo" in result.output
    assert not (claude_dir() / "skills/extra.md").exists()


def test_exact_pull_asks_on_a_terminal(pushed, monkeypatch):
    monkeypatch.setattr(restore_commands, "stdin_is_interactive", lambda: True)
    declined = _invoke("pull", "--exact", stdin="n\n")
    assert declined.exit_code == 1 and "Nothing was changed" in declined.output
    assert (claude_dir() / "skills/extra.md").exists()

    accepted = _invoke("pull", "--exact", stdin="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert not (claude_dir() / "skills/extra.md").exists()


def test_overlay_pull_never_asks(pushed):
    result = _invoke("pull")
    assert result.exit_code == 0, result.output
    assert (claude_dir() / "skills/extra.md").exists()
    assert "Kept 1 file(s)" in result.output


def test_diff_always_lists_only_local_files(pushed):
    result = _invoke("diff")
    assert result.exit_code == 0, result.output
    assert "Only on this machine (1)" in result.output
    assert "`pull --exact` would remove them" in result.output
    assert "Delete (0)" in result.output


def test_long_lists_are_capped_unless_all(pushed):
    write_files(claude_dir(), {f"skills/many{i:02}.md": "x" for i in range(25)})
    capped = _invoke("diff")
    assert "and 6 more (use --all" in capped.output  # 26 local extras, 20 shown
    full = _invoke("diff", "--all")
    assert "more (use --all" not in full.output and "skills/many24.md" in full.output


def test_undo_command_round_trip_and_conflict(pushed):
    assert _invoke("pull", "--exact", "--yes").exit_code == 0
    write_files(claude_dir(), {"CLAUDE.md": "# changed again"})
    refused = _invoke("undo")
    assert refused.exit_code == 1
    assert "Changed since the pull (1)" in refused.output and "--force" in refused.output

    forced = _invoke("undo", "--force")
    assert forced.exit_code == 0, forced.output
    assert (claude_dir() / "skills/extra.md").read_text() == "x"
    assert (claude_dir() / "CLAUDE.md").read_text() == "# edited"
    assert "There is no pull to undo" in _invoke("undo").output


def test_status_command(pushed):
    result = _invoke("status")
    assert result.exit_code == 0, result.output
    assert "Last synced: snapshot #1" in result.output
    assert "1 added, 1 modified, 0 removed" in result.output
    assert "nothing newer" in result.output
    assert "claude-cfg push" in result.output

    offline = _invoke("status", "--offline")
    assert "not checked" in offline.output


def test_status_command_without_state(pushed):
    state_file().unlink()
    result = _invoke("status")
    assert "never on this machine" in result.output
    assert "newer than this machine" in result.output
    assert "claude-cfg pull" in result.output


def test_help_lists_restore_commands():
    help_text = _invoke("--help").output
    assert all(name in help_text for name in ("diff", "undo", "status"))
    pull_help = _invoke("pull", "--help").output
    assert all(flag in pull_help for flag in ("--dry-run", "--exact", "--yes", "--all"))
