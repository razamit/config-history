"""Running external commands through an injectable seam.

Everything that shells out (the ``claude mcp`` calls) takes a
:class:`CommandRunner`, so tests can replace it and never reach a real
binary. Input that may hold secrets goes on stdin, never in the arguments,
because arguments are visible to other local processes.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

DEFAULT_TIMEOUT_SECONDS = 60


class CommandNotFoundError(FileNotFoundError):
    """The program to run is not on PATH."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


class CommandRunner(Protocol):
    def run(self, arguments: Sequence[str], stdin_text: Optional[str] = None) -> CommandResult:
        """Run ``arguments`` with ``stdin_text`` on stdin.

        Raises :class:`CommandNotFoundError` when the program is missing.
        """
        ...


class SubprocessCommandRunner:
    """Runs a real program, found on PATH, with captured output."""

    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    def run(self, arguments: Sequence[str], stdin_text: Optional[str] = None) -> CommandResult:
        program = shutil.which(arguments[0])
        if program is None:
            raise CommandNotFoundError(arguments[0])
        completed = subprocess.run(
            [program, *arguments[1:]],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)
