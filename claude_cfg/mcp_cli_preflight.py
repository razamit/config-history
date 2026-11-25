"""Checks that run before any ``claude mcp`` command changes a server.

A replace is a remove followed by an add, so starting one that cannot finish
loses the server. These checks decide up front whether MCP changes can be
applied at all, and the whole MCP step is skipped when they cannot.
"""

import os
import re
import subprocess
from typing import Mapping, Optional

from claude_cfg.command_runner import CommandNotFoundError, CommandRunner

# Reading a definition from stdin (``add-json <name> -``) arrived in this release.
MINIMUM_CLAUDE_VERSION = (2, 1, 327)
CLAUDE_CODE_SESSION_ENV = "CLAUDECODE"
NOT_FOUND_REASON = "the `claude` command was not found on PATH"
INSIDE_SESSION_REASON = (
    "this ran inside a Claude Code session, where `claude mcp add-json` must not run. "
    "Run the command again from a normal terminal to apply MCP server changes"
)

_SERVER_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")
_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def is_valid_server_name(name: object) -> bool:
    """Letters, digits, ``_``, ``.`` and ``-``, not starting with ``-``, so a
    name can never be read as an option on a command line."""
    return isinstance(name, str) and bool(_SERVER_NAME_PATTERN.fullmatch(name)) and not name.startswith("-")


def parse_version(text: str) -> Optional[tuple[int, int, int]]:
    match = _VERSION_PATTERN.search(text)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def _format_version(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


class McpCliPreflight:
    """Answers "can MCP changes be applied here?" through an injected runner."""

    def __init__(
        self,
        runner: CommandRunner,
        program: str,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._runner = runner
        self._program = program
        self._environ = os.environ if environ is None else environ

    def problem(self) -> Optional[str]:
        """None when changes can go ahead, otherwise why they cannot."""
        if self._environ.get(CLAUDE_CODE_SESSION_ENV):
            return INSIDE_SESSION_REASON
        return self._version_problem()

    def _version_problem(self) -> Optional[str]:
        try:
            completed = self._runner.run([self._program, "--version"], None)
        except CommandNotFoundError:
            return NOT_FOUND_REASON
        except (subprocess.TimeoutExpired, OSError) as error:
            return f"`claude --version` could not be run ({type(error).__name__})"
        version = parse_version(completed.stdout) if completed.succeeded else None
        needed = _format_version(MINIMUM_CLAUDE_VERSION)
        if version is None:
            return f"the Claude Code version could not be read; MCP restore needs {needed} or later"
        if version < MINIMUM_CLAUDE_VERSION:
            return (
                f"Claude Code {_format_version(version)} is too old; MCP restore needs "
                f"{needed} or later. Update Claude Code and pull again"
            )
        return None
