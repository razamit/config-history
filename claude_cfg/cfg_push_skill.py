"""The ``/cfg-push`` skill that ``claude-cfg integrate install`` writes.

The file carries a marker line, so ``integrate remove`` only ever deletes a
skill this tool wrote and leaves a hand-written one of the same name alone.
"""

import os
from enum import Enum
from pathlib import Path

SKILL_NAME = "cfg-push"
SKILL_MARKER = "<!-- claude-cfg integrate: written by claude-cfg. `claude-cfg integrate remove` deletes it. -->"

SKILL_TEXT = f"""---
description: Push the current Claude Code config as a claude-cfg snapshot.
argument-hint: [message]
disable-model-invocation: true
allowed-tools: Bash(claude-cfg push *)
---
{SKILL_MARKER}

Run `claude-cfg push "<message>"`, where the message is the text the user
typed after the command: $ARGUMENTS

Put the message in double quotes and escape any double quotes inside it. If
the user gave no text, run `claude-cfg push ""`. Do not run anything else.
When it finishes, report the line it printed, such as
"Snapshot #12 pushed", or the error if it failed.
"""


class SkillState(str, Enum):
    MISSING = "missing"
    OURS = "installed"
    FOREIGN = "not written by claude-cfg"


class CfgPushSkill:
    """Installs and removes ``skills/cfg-push/SKILL.md`` under the Claude folder."""

    def __init__(self, claude_dir: Path) -> None:
        self._folder = claude_dir / "skills" / SKILL_NAME
        self._path = self._folder / "SKILL.md"

    @property
    def path(self) -> Path:
        return self._path

    def state(self) -> SkillState:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return SkillState.MISSING
        except (OSError, UnicodeDecodeError):
            return SkillState.FOREIGN
        return SkillState.OURS if SKILL_MARKER in text else SkillState.FOREIGN

    def install(self) -> SkillState:
        """Write the skill unless someone else's file is in the way.

        Returns the state found before writing.
        """
        found = self.state()
        if found is not SkillState.FOREIGN:
            self._folder.mkdir(parents=True, exist_ok=True)
            partial_path = self._path.with_name(self._path.name + ".partial")
            partial_path.write_text(SKILL_TEXT, encoding="utf-8")
            os.replace(partial_path, self._path)
        return found

    def remove(self) -> SkillState:
        """Delete the skill only when it is ours. Returns the state found."""
        found = self.state()
        if found is SkillState.OURS:
            self._path.unlink()
            if not any(self._folder.iterdir()):
                self._folder.rmdir()
        return found
