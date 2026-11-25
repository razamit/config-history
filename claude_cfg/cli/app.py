"""The Typer application and command registration."""

from typing import Optional

import typer

from claude_cfg import __version__
from claude_cfg.cli.autosave_commands import autosave_command, config_autosave_command
from claude_cfg.cli.config_commands import config_app
from claude_cfg.cli.error_boundary import ErrorReportingGroup
from claude_cfg.cli.init_command import init_command
from claude_cfg.cli.integrate_commands import integrate_app
from claude_cfg.cli.restore_commands import diff_command, pull_command, undo_command
from claude_cfg.cli.session_hook_commands import session_hook_app
from claude_cfg.cli.snapshot_commands import list_command, push_command
from claude_cfg.cli.status_command import status_command
from claude_cfg.program_name import program_name

app = typer.Typer(
    name="claude-cfg",
    help="Versioned history of your Claude Code settings, kept locally or synced to a backend.",
    no_args_is_help=True,
    cls=ErrorReportingGroup,
    pretty_exceptions_show_locals=False,
)

SAVE_HELP = "Save your current Claude Code settings as a new version. Same as push."
HISTORY_HELP = "List the saved versions, newest first. Same as list."
RESTORE_HELP = (
    "Put your Claude Code settings back to a saved version (the latest by default). "
    "Same as pull."
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{program_name()} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Versioned history of your Claude Code settings, kept locally or synced to a backend."""


app.command("init")(init_command)
app.command("push")(push_command)
app.command("save", help=SAVE_HELP)(push_command)
app.command("pull")(pull_command)
app.command("restore", help=RESTORE_HELP)(pull_command)
app.command("list")(list_command)
app.command("history", help=HISTORY_HELP)(list_command)
app.command("diff")(diff_command)
app.command("undo")(undo_command)
app.command("status")(status_command)
app.command("autosave")(autosave_command)
config_app.command("autosave")(config_autosave_command)
app.add_typer(config_app, name="config")
app.add_typer(integrate_app, name="integrate")
app.add_typer(session_hook_app, name="session-hook")
