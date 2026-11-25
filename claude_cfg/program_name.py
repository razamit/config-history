"""The name the user types to run this tool, for every hint the CLI prints.

The tool ships as the ``claude-cfg`` command and also inside a Claude Code
plugin that runs it as ``config-history``. The plugin sets
``CLAUDE_CFG_PROGRAM_NAME`` so hints name the command the user actually has.

Inside the plugin, ``config-history`` is on the PATH of Claude's shell tool
only, so a person cannot type it in their own terminal. Hints there name the
plugin's slash commands instead, such as ``/config-history:restore``. A
command no slash command covers (``undo --force``, ``config track-defaults``)
is worded as a request to Claude in plain words, with the command Claude
runs in brackets (:func:`ask_claude_text`). A command that asks the person a
question (``config encrypt``) cannot run through Claude, so the plugin names
the ``claude-cfg`` command and says to run it in a terminal
(:func:`terminal_command_text`). That only comes up after the user set up
encryption or a sync backend with ``claude-cfg`` in a terminal.
"""

import os
import re
from typing import Mapping, Optional

PROGRAM_NAME_ENV = "CLAUDE_CFG_PROGRAM_NAME"
DEFAULT_PROGRAM_NAME = "claude-cfg"
PLUGIN_PROGRAM_NAME = "config-history"

# A command name, optionally with arguments such as "python3 -m claude_cfg".
# Anything else (control characters, quotes, very long text) is ignored.
_ACCEPTED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/ -]{0,63}$")

RESTORE_SLASH_COMMAND = "/config-history:restore"
UNDO_SLASH_COMMAND = "/config-history:undo"
HISTORY_SLASH_COMMAND = "/config-history:history"

# The slash command for each verb, and whether the verb's arguments may be
# dropped. The restore skill picks the version itself and the history skill
# answers in plain words, so their arguments are not needed. ``undo`` maps
# only without arguments, since the undo skill passes none.
_SLASH_COMMANDS = {
    "restore": (RESTORE_SLASH_COMMAND, True),
    "pull": (RESTORE_SLASH_COMMAND, True),
    "undo": (UNDO_SLASH_COMMAND, False),
    "history": (HISTORY_SLASH_COMMAND, True),
    "list": (HISTORY_SLASH_COMMAND, True),
    "diff": (HISTORY_SLASH_COMMAND, True),
    "status": (HISTORY_SLASH_COMMAND, True),
    "save": (HISTORY_SLASH_COMMAND + " save", True),
    "push": (HISTORY_SLASH_COMMAND + " save", True),
}


def program_name(environ: Optional[Mapping[str, str]] = None) -> str:
    """``CLAUDE_CFG_PROGRAM_NAME`` when it is set to a plain name, else ``claude-cfg``."""
    source = os.environ if environ is None else environ
    configured = source.get(PROGRAM_NAME_ENV, "").strip()
    if configured and _ACCEPTED_NAME.match(configured):
        return configured
    return DEFAULT_PROGRAM_NAME


def uses_slash_commands(environ: Optional[Mapping[str, str]] = None) -> bool:
    """True when the tool runs as the plugin, so people type slash commands."""
    return program_name(environ) == PLUGIN_PROGRAM_NAME


def slash_command_for(arguments: str) -> Optional[str]:
    """The plugin slash command that does what ``arguments`` does, or None."""
    words = arguments.split()
    if not words or words[0] not in _SLASH_COMMANDS:
        return None
    slash_command, arguments_optional = _SLASH_COMMANDS[words[0]]
    if len(words) > 1 and not arguments_optional:
        return None
    return slash_command


def shell_command_hint(arguments: str = "") -> str:
    """The shell form, such as ``claude-cfg undo``, for a normal terminal or for Claude."""
    return f"{program_name()} {arguments}".strip()


def ask_claude_phrase(arguments: str, request: str) -> str:
    """Inside the plugin, a command no slash command covers, as what to ask
    Claude: ``ask Claude to turn it on (it runs `config-history config
    autosave --enable`)``. ``request`` is the plain words after "ask Claude to"."""
    return f"ask Claude to {request} (it runs `{shell_command_hint(arguments)}`)"


def ask_claude_text(arguments: str, request: str) -> str:
    """:func:`ask_claude_phrase` as a whole sentence."""
    return f"A{ask_claude_phrase(arguments, request)[1:]}."


def terminal_command_hint(arguments: str = "") -> str:
    """A command only a person at a terminal can run, because it asks a
    question or must run outside Claude Code. Claude's shell cannot answer a
    prompt, so inside the plugin this names the ``claude-cfg`` command, which
    reads the same tool folder; elsewhere it is :func:`shell_command_hint`."""
    if uses_slash_commands():
        return f"{DEFAULT_PROGRAM_NAME} {arguments}".strip()
    return shell_command_hint(arguments)


def terminal_command_text(arguments: str = "") -> str:
    """:func:`terminal_command_hint` in backticks, followed by "in a terminal"
    inside the plugin, where the user would otherwise read it as a request to Claude."""
    quoted = f"`{terminal_command_hint(arguments)}`"
    return f"{quoted} in a terminal" if uses_slash_commands() else quoted


def command_hint(arguments: str = "") -> str:
    """What the user types to run ``arguments``: the slash command inside the
    plugin when one covers it, else the shell command such as ``claude-cfg undo --force``."""
    if uses_slash_commands():
        slash_command = slash_command_for(arguments)
        if slash_command is not None:
            return slash_command
    return shell_command_hint(arguments)
