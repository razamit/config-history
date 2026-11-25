"""Things every command needs: config loading, error reporting, prompts."""

from contextlib import contextmanager
from typing import Callable, Iterator

import typer
from rich.status import Status

from claude_cfg.cli.error_boundary import is_click_control_flow, report_unexpected
from claude_cfg.cli.output import print_error
from claude_cfg.default_history import load_or_create_config
from claude_cfg.errors import ClaudeCfgError
from claude_cfg.paths import config_file

PASSPHRASE_PROMPT_TEXT = "Snapshot passphrase"
REPEAT_PROMPT_TEXT = "Repeat the passphrase"


def load_config_or_exit() -> dict:
    """The saved config. With none yet, the automatic local-history config,
    written now, so commands work before any setup."""
    try:
        return load_or_create_config()
    except (OSError, ValueError) as error:
        print_error(f"Could not read the config at {config_file()}: {error}")
        raise typer.Exit(1)


@contextmanager
def reported_errors() -> Iterator[None]:
    """Print a failure as one red line and exit with status 1.

    Expected errors keep their message; anything else is shown with its type
    name, the same as the app-wide boundary in :mod:`error_boundary`.
    """
    try:
        yield
    except ClaudeCfgError as error:
        print_error(str(error))
        raise typer.Exit(1)
    except Exception as error:  # noqa: BLE001 - this is the CLI boundary
        if is_click_control_flow(error):
            raise
        report_unexpected(error)
        raise typer.Exit(1) from None


def prompt_existing_passphrase(text: str = PASSPHRASE_PROMPT_TEXT) -> str:
    return typer.prompt(text, hide_input=True)


def passphrase_prompt_pausing(status: Status, text: str = PASSPHRASE_PROMPT_TEXT) -> Callable[[], str]:
    """A passphrase prompt that hides a running spinner while it asks."""

    def prompt() -> str:
        status.stop()
        try:
            return prompt_existing_passphrase(text)
        finally:
            status.start()

    return prompt
