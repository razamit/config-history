"""Backend-supplied text is shown without hidden characters and without
being read as rich markup."""

import io
import json
import zipfile

import pytest
from typer.testing import CliRunner

from claude_cfg import config as cfg_mod
from claude_cfg.cli import app, output
from claude_cfg.display_text import printable_text
from claude_cfg.paths import claude_dir
from claude_cfg.providers import get_provider
from claude_cfg.session_start_notice import newer_snapshot_message
from claude_cfg.snapshot_index import SnapshotEntry
from claude_cfg.sync_status import RemoteStatus
from tests.sync_helpers import store_raw_zip, write_files

BIDI = chr(0x202E)
LINE_SEPARATOR = chr(0x2028)
PARAGRAPH_SEPARATOR = chr(0x2029)
ZERO_WIDTH_SPACE = chr(0x200B)
MESSAGE = f"[red]x[/red] {BIDI}ab[/dim]"
MACHINE = f"[bold]box{LINE_SEPARATOR}two{ZERO_WIDTH_SPACE}"


def _hostile_snapshot() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CLAUDE.md", "# theirs")
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 4, "id": 1, "timestamp": "2026-01-01T00:00:00Z",
            "message": MESSAGE, "machine": MACHINE, "files": ["CLAUDE.md"], "tracked": ["CLAUDE.md"],
        }))
    return buffer.getvalue()


@pytest.fixture
def hostile_backend(isolated_home, monkeypatch):
    write_files(claude_dir(), {"CLAUDE.md": "# mine"})
    cfg = {"storage": "local", "tracked": ["CLAUDE.md"], "local": {"path": str(isolated_home / "store")}}
    cfg_mod.save(cfg)
    store_raw_zip(get_provider(cfg), _hostile_snapshot())
    monkeypatch.setattr(output.console, "width", 300)


def _assert_safe(text: str) -> None:
    assert "[red]x[/red]" in text, text
    assert all(c not in text for c in (BIDI, LINE_SEPARATOR, ZERO_WIDTH_SPACE))


def test_printable_text_drops_control_format_and_separator_characters():
    hidden = f"a\nb\x1b[31m{BIDI}c{LINE_SEPARATOR}d{PARAGRAPH_SEPARATOR}e{ZERO_WIDTH_SPACE}f"
    assert printable_text(hidden) == "ab[31mcdef"


def test_list_diff_pull_and_status_show_the_text_literally(hostile_backend):
    cli = CliRunner()
    for command in (["list"], ["diff"], ["pull", "--dry-run"], ["pull"]):
        result = cli.invoke(app, command)
        assert result.exit_code == 0, result.output
        _assert_safe(result.output)
    status = cli.invoke(app, ["status", "--offline"])
    assert status.exit_code == 0, status.output
    assert "[bold]boxtwo" in status.output and BIDI not in status.output


def test_init_summary_shows_the_text_literally():
    with output.console.capture() as captured:
        output.print_snapshot_summary(
            [{"id": 1, "timestamp": "2026-01-01T00:00:00Z", "message": MESSAGE, "machine": MACHINE}]
        )
    _assert_safe(captured.get())
    assert "[bold]boxtwo" in captured.get()


def test_hook_notice_strips_bidi_and_separators():
    entry = SnapshotEntry(2, "2026-01-01T00:00:00Z", "k", message=MESSAGE, machine=MACHINE, encrypted=False)
    notice = newer_snapshot_message(RemoteStatus(checked=True, latest=entry, is_newer=True))
    assert all(c not in notice for c in (BIDI, LINE_SEPARATOR, ZERO_WIDTH_SPACE))
    assert "[bold]boxtwo" in notice
