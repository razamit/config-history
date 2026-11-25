"""How hints and headings name commands and versions.

The tool started as a sync tool, so its words are ``push``, ``pull`` and
"snapshot #N". People who only keep the local history (the automatic default
config, or the ``config-history`` plugin) think in ``save``, ``restore`` and
"version N", and their history is on this machine, so there is no remote to
report. :func:`wording_for` picks the words once; output code asks it instead
of checking the config itself. A backend set up with ``init`` under the
``claude-cfg`` name keeps the sync words.
"""

from dataclasses import dataclass
from typing import Optional

from claude_cfg.config import is_automatic_default
from claude_cfg.config import load as load_config
from claude_cfg.program_name import command_hint, program_name

LOCAL_HISTORY_PROGRAM_NAME = "config-history"


@dataclass(frozen=True)
class CommandWording:
    """``local_words``: save, restore and version N. ``history_on_this_machine``:
    the history is the automatic local one, so there is no remote to report."""

    local_words: bool = False
    history_on_this_machine: bool = False

    @property
    def save_verb(self) -> str:
        return "save" if self.local_words else "push"

    @property
    def restore_verb(self) -> str:
        return "restore" if self.local_words else "pull"

    @property
    def saved_word(self) -> str:
        return "saved" if self.local_words else "pushed"

    def command(self, verb: str, arguments: str = "") -> str:
        """The full command, such as ``config-history restore --exact``."""
        return command_hint(f"{verb} {arguments}".strip())

    def exact_restore_hint(self) -> str:
        """How to also remove local extras: the full command in local wording."""
        if self.local_words:
            return self.command(self.restore_verb, "--exact")
        return "pull --exact"

    def version_label(self, number: object, markup: bool = False) -> str:
        """``Version 3`` or ``Snapshot #3``, optionally with the number in cyan."""
        shown_number = f"[cyan]{number}[/cyan]" if markup else str(number)
        if self.local_words:
            return f"Version {shown_number}"
        hashed = f"[cyan]#{number}[/cyan]" if markup else f"#{number}"
        return f"Snapshot {hashed}"

    def version_noun(self, number: object) -> str:
        """``version 3`` or ``snapshot #3``, for the middle of a sentence."""
        return f"version {number}" if self.local_words else f"snapshot #{number}"


def wording_for(cfg: Optional[dict]) -> CommandWording:
    """The words for this config and the program name the user types."""
    local_history = cfg is not None and is_automatic_default(cfg)
    local_words = local_history or program_name() == LOCAL_HISTORY_PROGRAM_NAME
    return CommandWording(local_words=local_words, history_on_this_machine=local_history)


def wording_for_saved_config() -> CommandWording:
    """:func:`wording_for` the saved config, or the program name alone without one."""
    try:
        cfg = load_config()
    except (OSError, ValueError):
        cfg = None
    return wording_for(cfg if isinstance(cfg, dict) else None)
