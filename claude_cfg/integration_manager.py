"""``claude-cfg integrate``: the session hooks and the /cfg-push skill."""

from dataclasses import dataclass
from pathlib import Path

from claude_cfg.cfg_push_skill import CfgPushSkill, SkillState
from claude_cfg.claude_settings_file import ClaudeSettingsFile
from claude_cfg.errors import SettingsFileError
from claude_cfg.session_hook_settings import (
    add_session_hook,
    has_session_hook,
    hooks_up_to_date,
    remove_session_hook,
)


@dataclass(frozen=True)
class IntegrationReport:
    """``hook_changed`` says whether settings.json was rewritten.
    ``skill_found`` is the skill's state before the command ran."""

    hook_changed: bool
    skill_found: SkillState
    settings_path: Path
    skill_path: Path


@dataclass(frozen=True)
class IntegrationStatus:
    hook_installed: bool
    skill: SkillState
    settings_path: Path
    skill_path: Path
    # False when an older or partial set of hooks is installed.
    hook_current: bool = True


class IntegrationManager:
    """Installs, removes and reports the Claude Code integration."""

    def __init__(self, settings_file: ClaudeSettingsFile, skill: CfgPushSkill) -> None:
        self._settings_file = settings_file
        self._skill = skill

    @classmethod
    def for_claude_dir(cls, claude_dir: Path) -> "IntegrationManager":
        return cls(ClaudeSettingsFile(claude_dir / "settings.json"), CfgPushSkill(claude_dir))

    def install(self) -> IntegrationReport:
        settings = self._settings_file.load()
        hook_changed = add_session_hook(settings)
        if hook_changed:
            self._settings_file.save(settings)
        return self._report(hook_changed, self._skill.install())

    def remove(self) -> IntegrationReport:
        settings = self._settings_file.load()
        hook_changed = remove_session_hook(settings)
        if hook_changed:
            self._settings_file.save(settings)
        return self._report(hook_changed, self._skill.remove())

    def status(self) -> IntegrationStatus:
        settings = self._settings_file.load()
        return IntegrationStatus(
            hook_installed=has_session_hook(settings),
            skill=self._skill.state(),
            settings_path=self._settings_file.path,
            skill_path=self._skill.path,
            hook_current=hooks_up_to_date(settings),
        )

    def hook_installed(self) -> bool:
        """Whether the hook is in settings.json. False when the file is unreadable."""
        try:
            return has_session_hook(self._settings_file.load())
        except SettingsFileError:
            return False

    def _report(self, hook_changed: bool, skill_found: SkillState) -> IntegrationReport:
        return IntegrationReport(hook_changed, skill_found, self._settings_file.path, self._skill.path)
