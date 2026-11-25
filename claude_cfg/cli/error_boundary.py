"""The one place where an unexpected failure becomes a short error line.

Every command runs inside :class:`ErrorReportingGroup`, so any exception,
not only a :class:`ClaudeCfgError`, ends as one line and exit status 1.
Tracebacks are off by default because a frame's locals can hold the config,
a passphrase, a token or an MCP definition. ``CLAUDE_CFG_DEBUG=1`` prints the
standard traceback, which shows code lines but never local values.
"""

import os
import sys
import traceback
from typing import Any, Mapping, Optional

import typer
from typer.core import TyperGroup

from claude_cfg.cli.output import print_error
from claude_cfg.errors import ClaudeCfgError

DEBUG_ENV_VAR = "CLAUDE_CFG_DEBUG"


def is_click_control_flow(error: BaseException) -> bool:
    """Exit, Abort and usage errors are Typer's own way to end a command."""
    return type(error).__module__.startswith(("typer", "click"))


def debug_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if environ is None else environ
    return source.get(DEBUG_ENV_VAR, "").strip() == "1"


def error_line(error: BaseException) -> str:
    """The message shown for ``error``. Expected errors keep their own wording."""
    if isinstance(error, ClaudeCfgError):
        return str(error)
    message = str(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def report_unexpected(error: BaseException) -> None:
    print_error(error_line(error))
    if debug_enabled():
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


class ErrorReportingGroup(TyperGroup):
    """A Typer group whose commands never end in a traceback."""

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except Exception as error:  # noqa: BLE001 - this is the CLI boundary
            if is_click_control_flow(error):
                raise
            report_unexpected(error)
            raise typer.Exit(1) from None
