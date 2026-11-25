"""The name the user types to run this tool, for every hint the CLI prints.

The tool ships as the ``claude-cfg`` command and also inside a Claude Code
plugin that runs it as ``config-history``. The plugin sets
``CLAUDE_CFG_PROGRAM_NAME`` so hints such as "Run ... undo" name the command
the user actually has.
"""

import os
import re
from typing import Mapping, Optional

PROGRAM_NAME_ENV = "CLAUDE_CFG_PROGRAM_NAME"
DEFAULT_PROGRAM_NAME = "claude-cfg"

# A command name, optionally with arguments such as "python3 -m claude_cfg".
# Anything else (control characters, quotes, very long text) is ignored.
_ACCEPTED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/ -]{0,63}$")


def program_name(environ: Optional[Mapping[str, str]] = None) -> str:
    """``CLAUDE_CFG_PROGRAM_NAME`` when it is set to a plain name, else ``claude-cfg``."""
    source = os.environ if environ is None else environ
    configured = source.get(PROGRAM_NAME_ENV, "").strip()
    if configured and _ACCEPTED_NAME.match(configured):
        return configured
    return DEFAULT_PROGRAM_NAME


def command_hint(arguments: str = "") -> str:
    """The full command to type, such as ``claude-cfg undo --force``."""
    return f"{program_name()} {arguments}".strip()
