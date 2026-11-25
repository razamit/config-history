"""Command runners for tests. None of them start a process."""

from dataclasses import dataclass, field
from typing import Optional, Sequence

from claude_cfg.command_runner import CommandNotFoundError, CommandResult


@dataclass
class RecordedCall:
    arguments: list[str]
    stdin_text: Optional[str]


@dataclass
class RecordingRunner:
    """Records every ``claude mcp`` call. ``fail_on`` maps a sub-command such
    as "add-json" to the exit status it should return; ``fail_counts`` makes
    only the first N calls of a sub-command fail. ``claude --version`` is
    answered with ``version_output`` and not recorded."""

    fail_on: dict[str, int] = field(default_factory=dict)
    calls: list[RecordedCall] = field(default_factory=list)
    version_output: str = "2.1.330 (Claude Code)"
    fail_counts: dict[str, int] = field(default_factory=dict)

    def run(self, arguments: Sequence[str], stdin_text: Optional[str] = None) -> CommandResult:
        if list(arguments[1:]) == ["--version"]:
            return CommandResult(0, self.version_output, "")
        self.calls.append(RecordedCall(list(arguments), stdin_text))
        step = arguments[2] if len(arguments) > 2 else ""
        if self.fail_counts.get(step, 0) > 0:
            self.fail_counts[step] -= 1
            return CommandResult(1, "", "secret-looking stderr that must never be shown")
        status = self.fail_on.get(step, 0)
        return CommandResult(status, "", "secret-looking stderr that must never be shown")


class MissingProgramRunner:
    """Behaves as if ``claude`` is not on PATH."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, arguments: Sequence[str], stdin_text: Optional[str] = None) -> CommandResult:
        self.calls += 1
        raise CommandNotFoundError(arguments[0])
