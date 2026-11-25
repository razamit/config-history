"""Applying and reverting MCP server changes through the ``claude mcp`` CLI.

``.claude.json`` is never written here. Every change is a documented command:
``claude mcp remove <name> --scope user`` and
``claude mcp add-json <name> - --scope user`` with the definition on stdin.
Definitions never go in the arguments and never appear in a failure reason.

Before any command runs, :class:`McpCliPreflight` checks that changes can be
applied at all, and server names are checked so none can look like an option.
A replace whose add fails right after its remove puts the previous
definition straight back.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Mapping, Optional

from claude_cfg.command_runner import CommandNotFoundError, CommandRunner
from claude_cfg.mcp_cli_preflight import NOT_FOUND_REASON, McpCliPreflight, is_valid_server_name
from claude_cfg.mcp_server_capture import McpServers
from claude_cfg.mcp_server_plan import McpServerPlan

CLAUDE_PROGRAM = "claude"
INVALID_NAME_REASON = "skipped, the server name has characters a command line cannot take safely"
ROLLED_BACK_NOTE = "the previous definition was put back"
ROLLBACK_FAILED_NOTE = "putting the previous definition back also failed, so the server is missing now"


@dataclass
class McpApplyResult:
    """Server names that were applied, and why the others were not."""

    applied: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    rolled_back: list[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None


@dataclass
class McpBackupRecord:
    """What a pull did to MCP servers, with what it takes to put them back.

    ``replaced`` and ``removed`` hold the previous definitions, so a backup
    manifest that carries this record holds secrets and must stay private.
    """

    added: list[str] = field(default_factory=list)
    replaced: McpServers = field(default_factory=dict)
    removed: McpServers = field(default_factory=dict)

    @classmethod
    def from_plan(cls, plan: McpServerPlan) -> "McpBackupRecord":
        previous = plan.previous_definitions
        return cls(
            added=list(plan.to_add),
            replaced={name: previous[name] for name in plan.to_replace},
            removed={name: previous[name] for name in plan.to_remove},
        )

    @classmethod
    def from_dict(cls, document: object) -> Optional["McpBackupRecord"]:
        if not isinstance(document, dict):
            return None
        added, replaced, removed = (document.get(k) for k in ("added", "replaced", "removed"))
        if not isinstance(added, list) or not isinstance(replaced, dict) or not isinstance(removed, dict):
            return None
        return cls(added=[str(n) for n in added], replaced=replaced, removed=removed)

    def to_dict(self) -> dict:
        return {"added": list(self.added), "replaced": dict(self.replaced), "removed": dict(self.removed)}

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.replaced or self.removed)

    def keep_applied(self, result: McpApplyResult) -> None:
        """Forget changes that never happened or were already put back.

        A failed replace stays only when its previous definition could not be
        put back, so undo can try again.
        """
        self.added = [name for name in self.added if name in result.applied]
        self.removed = {n: d for n, d in self.removed.items() if n in result.applied}
        self.replaced = {
            name: definition
            for name, definition in self.replaced.items()
            if name in result.applied or (name in result.failed and name not in result.rolled_back)
        }


class McpServerSyncManager:
    """Runs the ``claude mcp`` commands a plan or a backup record calls for."""

    def __init__(
        self,
        runner: CommandRunner,
        program: str = CLAUDE_PROGRAM,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._runner = runner
        self._program = program
        self._preflight = McpCliPreflight(runner, program, environ)
        self._program_missing = False

    def preflight_problem(self) -> Optional[str]:
        """Why MCP changes cannot be applied here, or None when they can."""
        return self._preflight.problem()

    def apply(self, plan: McpServerPlan) -> McpApplyResult:
        result = self._checked_result(plan.to_remove + plan.to_replace + plan.to_add)
        if result.skipped_reason is not None:
            return result
        for name in self._valid(plan.to_remove):
            self._record(result, name, self._remove(name))
        for name in self._valid(plan.to_replace):
            self._replace(result, name, plan.definitions[name], plan.previous_definitions.get(name))
        for name in self._valid(plan.to_add):
            self._record(result, name, self._add(name, plan.definitions[name]))
        return result

    def revert(self, record: McpBackupRecord) -> McpApplyResult:
        """Undo a pull: remove what it added, put back what it replaced or removed."""
        names = list(record.added) + list(record.replaced) + list(record.removed)
        result = self._checked_result(names)
        if result.skipped_reason is not None:
            return result
        for name in self._valid(record.added):
            self._record(result, name, self._remove(name))
        for name in self._valid(record.replaced):
            # The pull may have left nothing to remove, so only the add counts.
            self._remove(name)
            self._record(result, name, self._add(name, record.replaced[name]))
        for name in self._valid(record.removed):
            self._record(result, name, self._add(name, record.removed[name]))
        return result

    def _checked_result(self, names: list[str]) -> McpApplyResult:
        """A result with invalid names failed and, when nothing can run, the reason."""
        result = McpApplyResult()
        for name in names:
            if not is_valid_server_name(name):
                result.failed[str(name)] = INVALID_NAME_REASON
        if any(is_valid_server_name(name) for name in names):
            result.skipped_reason = self._preflight.problem()
        return result

    @staticmethod
    def _valid(names) -> list[str]:
        return [name for name in names if is_valid_server_name(name)]

    def _replace(
        self, result: McpApplyResult, name: str, definition: dict, previous: Optional[dict]
    ) -> None:
        """Remove then add. When the add fails, add the previous definition back."""
        removal_failure = self._remove(name)
        if removal_failure is not None:
            self._record(result, name, removal_failure)
            return
        add_failure = self._add(name, definition)
        if add_failure is None or previous is None:
            self._record(result, name, add_failure)
            return
        if self._add(name, previous) is None:
            result.rolled_back.append(name)
            self._record(result, name, f"{add_failure}; {ROLLED_BACK_NOTE}")
        else:
            self._record(result, name, f"{add_failure}; {ROLLBACK_FAILED_NOTE}")

    @staticmethod
    def _record(result: McpApplyResult, name: str, failure: Optional[str]) -> None:
        if failure is None:
            result.applied.append(name)
        else:
            result.failed[name] = failure

    def _remove(self, name: str) -> Optional[str]:
        return self._run(["mcp", "remove", name, "--scope", "user"], None, "remove")

    def _add(self, name: str, definition: dict) -> Optional[str]:
        return self._run(
            ["mcp", "add-json", name, "-", "--scope", "user"], json.dumps(definition), "add-json"
        )

    def _run(self, arguments: list[str], stdin_text: Optional[str], step: str) -> Optional[str]:
        """None on success, otherwise a reason that never quotes the command's output."""
        if self._program_missing:
            return NOT_FOUND_REASON
        try:
            completed = self._runner.run([self._program, *arguments], stdin_text)
        except CommandNotFoundError:
            self._program_missing = True
            return NOT_FOUND_REASON
        except subprocess.TimeoutExpired:
            return f"`claude mcp {step}` timed out"
        except OSError as error:
            return f"`claude mcp {step}` could not be started ({type(error).__name__})"
        if not completed.succeeded:
            return f"`claude mcp {step}` exited with status {completed.returncode}"
        return None
