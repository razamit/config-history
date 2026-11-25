"""``list`` and its alias ``history``: plain words for the local history,
the sync table for a backend set up under the claude-cfg name."""

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.change_summary import change_text
from claude_cfg.cli import app, output
from claude_cfg.default_history import load_or_create_config
from claude_cfg.paths import claude_dir
from claude_cfg.program_name import PROGRAM_NAME_ENV
from tests.sync_helpers import write_files

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    monkeypatch.setattr(output.console, "width", 300)


@pytest.fixture
def local_history(isolated_home):
    write_files(claude_dir(), {"settings.json": '{"a": 1}', "CLAUDE.md": "# rules"})
    return load_or_create_config()


def invoke(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def row_for(listing: str, version: int) -> str:
    rows = [line for line in listing.splitlines() if line.strip("│ ").startswith(f"{version} ")]
    assert len(rows) == 1, listing
    return rows[0]


@pytest.mark.parametrize("message, automatic, expected", [
    ("auto: first version", True, "first version"),
    ("auto: 1 file changed (settings.json)", True, "settings.json changed"),
    ("auto: 2 files changed (settings.json, skills/demo/notes.md)", True,
     "settings.json, skills/demo/notes.md changed"),
    ("auto: 9 files changed (a.md, b.md and 7 more)", True, "a.md, b.md and 7 more changed"),
    ("auto: something else", True, "something else"),
    ("before cleanup", False, '"before cleanup" (saved by you)'),
    ("", False, "saved by you"),
    (None, False, "saved by you"),
])
def test_change_text(message, automatic, expected):
    assert change_text(message, automatic) == expected


def test_plain_history_for_automatic_first_and_hand_saved_versions(local_history):
    invoke("autosave")
    write_files(claude_dir(), {"settings.json": '{"a": 2}', "skills/demo/notes.md": "x"})
    invoke("autosave")
    invoke("save", "before cleanup")
    listing = invoke("list")
    header = listing.splitlines()[1]
    assert "Version" in header and "When" in header and "What changed" in header
    for hidden_column in ("Machine", "Encrypted", "Timestamp", "Message"):
        assert hidden_column not in listing
    assert "first version" in row_for(listing, 1)
    assert "settings.json, skills/demo/notes.md changed" in row_for(listing, 2)
    assert '"before cleanup" (saved by you)' in row_for(listing, 3)
    assert "just now (" in row_for(listing, 3)
    assert listing.index('"before cleanup"') < listing.index("first version"), "newest first"
    assert invoke("history") == listing


def test_plain_history_under_the_plugin_name_with_a_backend(monkeypatch, isolated_home):
    write_files(claude_dir(), {"CLAUDE.md": "# rules"})
    cfg_mod.save({"storage": "local", "tracked": ["CLAUDE.md"],
                  "local": {"path": str(isolated_home / "store")}})
    monkeypatch.setenv(PROGRAM_NAME_ENV, "config-history")
    invoke("save", "mine")
    listing = invoke("history")
    assert "What changed" in listing and "Machine" not in listing


def test_limit_and_the_line_about_older_versions(local_history):
    for number in range(1, 13):
        invoke("save", f"v{number}")
    default = invoke("history")
    assert '"v12"' in default and '"v3"' in default and '"v2"' not in default
    assert "2 older versions are not shown. Add --limit 12 to see every one." in default
    limited = invoke("list", "--limit", "1")
    assert '"v12"' in limited and '"v11"' not in limited
    assert "11 older versions are not shown." in limited
    everything = invoke("list", "--limit", "12")
    assert '"v1"' in everything and "not shown" not in everything


def test_limit_must_be_positive(local_history):
    result = runner.invoke(app, ["list", "--limit", "0"])
    assert result.exit_code != 0


def test_sync_backend_keeps_its_columns_with_local_times(isolated_home):
    write_files(claude_dir(), {"CLAUDE.md": "# rules"})
    cfg_mod.save({"storage": "local", "tracked": ["CLAUDE.md"],
                  "local": {"path": str(isolated_home / "store")}})
    for number in range(1, 13):
        invoke("push", f"p{number}")
    listing = invoke("list")
    for column in ("ID", "Timestamp", "Message", "Machine", "Encrypted"):
        assert column in listing
    assert "What changed" not in listing and "not shown" not in listing, "all rows by default"
    assert "just now (" in listing and "T" not in row_for(listing, 1).split("│")[2]
    assert "10 older snapshots are not shown." in invoke("list", "--limit", "2")


def test_empty_history_says_so(local_history):
    assert "No versions saved yet." in invoke("history")
