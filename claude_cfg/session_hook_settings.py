"""Adding and removing the claude-cfg session hooks in a settings dict.

The shape Claude Code reads is
``{"hooks": {"SessionStart": [{"matcher": ..., "hooks": [{"type": "command", ...}]}]}}``.
Two hooks are installed: ``session-hook start`` on SessionStart and
``session-hook end`` on SessionEnd. The older ``status --hook`` entry is
recognized, so install replaces it and remove takes it out. Only entries
whose command is exactly one of :data:`OUR_COMMANDS` are ever touched.
"""

from dataclasses import dataclass
from typing import Optional

from claude_cfg.errors import SettingsFileError


@dataclass(frozen=True)
class SessionHookSpec:
    event: str
    command: str
    timeout_seconds: int
    matcher: Optional[str] = None

    def entry(self) -> dict:
        return {"type": "command", "command": self.command, "timeout": self.timeout_seconds}

    def group(self) -> dict:
        group: dict = {"hooks": [self.entry()]}
        if self.matcher is not None:
            group = {"matcher": self.matcher, **group}
        return group


START_HOOK = SessionHookSpec("SessionStart", "claude-cfg session-hook start", 15, matcher="startup")
END_HOOK = SessionHookSpec("SessionEnd", "claude-cfg session-hook end", 30)
SESSION_HOOKS = (START_HOOK, END_HOOK)
LEGACY_HOOK_COMMAND = "claude-cfg status --hook"
OUR_COMMANDS = frozenset({START_HOOK.command, END_HOOK.command, LEGACY_HOOK_COMMAND})
OUR_EVENTS = ("SessionStart", "SessionEnd")

# Kept for callers that import the old single-hook names.
HOOK_COMMAND = START_HOOK.command
HOOK_EVENT = START_HOOK.event


def _is_our_entry(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("command") in OUR_COMMANDS


def _event_groups(settings: dict, event: str, create: bool) -> list:
    hooks = settings.get("hooks")
    if hooks is None and create:
        hooks = settings["hooks"] = {}
    if hooks is None:
        return []
    if not isinstance(hooks, dict):
        raise SettingsFileError('"hooks" in settings.json is not an object. Nothing was changed.')
    groups = hooks.get(event)
    if groups is None and create:
        groups = hooks[event] = []
    if groups is None:
        return []
    if not isinstance(groups, list):
        raise SettingsFileError(f'"hooks.{event}" in settings.json is not a list. Nothing was changed.')
    return groups


def _entries(settings: dict, event: str) -> list:
    return [
        entry
        for group in _event_groups(settings, event, create=False)
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        for entry in group["hooks"]
    ]


def has_session_hook(settings: dict) -> bool:
    """Whether any claude-cfg hook entry, current or old, is present."""
    return any(_is_our_entry(entry) for event in OUR_EVENTS for entry in _entries(settings, event))


def hooks_up_to_date(settings: dict) -> bool:
    """Each current hook exactly once in its own group, and nothing older."""
    for spec in SESSION_HOOKS:
        groups = [g for g in _event_groups(settings, spec.event, create=False) if isinstance(g, dict)]
        if sum(1 for g in groups if g == spec.group()) != 1:
            return False
        if sum(1 for entry in _entries(settings, spec.event) if _is_our_entry(entry)) != 1:
            return False
    return not any(
        entry.get("command") == LEGACY_HOOK_COMMAND
        for event in OUR_EVENTS
        for entry in _entries(settings, event)
        if isinstance(entry, dict)
    )


def add_session_hook(settings: dict) -> bool:
    """Install both hooks, replacing older or partial entries. False when
    the settings already have exactly the current hooks."""
    for event in OUR_EVENTS:
        _event_groups(settings, event, create=False)  # refuse odd shapes before changing anything
    if hooks_up_to_date(settings):
        return False
    remove_session_hook(settings)
    for spec in SESSION_HOOKS:
        _event_groups(settings, spec.event, create=True).append(spec.group())
    return True


def remove_session_hook(settings: dict) -> bool:
    """Remove our entries and any container that removal leaves empty."""
    removed_any = False
    for event in OUR_EVENTS:
        removed_any = _remove_from_event(settings, event) or removed_any
    return removed_any


def _remove_from_event(settings: dict, event: str) -> bool:
    groups = _event_groups(settings, event, create=False)
    removed_any = False
    for group in list(groups):
        entries = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(entries, list) or not any(_is_our_entry(e) for e in entries):
            continue
        group["hooks"] = [entry for entry in entries if not _is_our_entry(entry)]
        removed_any = True
        if not group["hooks"]:
            groups.remove(group)
    if removed_any:
        _drop_empty_containers(settings, event)
    return removed_any


def _drop_empty_containers(settings: dict, event: str) -> None:
    hooks = settings["hooks"]
    if not hooks[event]:
        del hooks[event]
    if not hooks:
        del settings["hooks"]
