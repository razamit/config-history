"""The ``claude-cfg integrate`` sub-commands."""

import typer
from rich.markup import escape

from claude_cfg.cfg_push_skill import SkillState
from claude_cfg.cli.command_context import reported_errors
from claude_cfg.cli.output import console
from claude_cfg.integration_manager import IntegrationManager
from claude_cfg.paths import claude_dir
from claude_cfg.program_name import command_hint
from claude_cfg.session_hook_settings import END_HOOK, START_HOOK

integrate_app = typer.Typer(
    help="Add or remove the Claude Code session hooks and the /cfg-push skill.",
    pretty_exceptions_show_locals=False,
)


def _manager() -> IntegrationManager:
    return IntegrationManager.for_claude_dir(claude_dir())


@integrate_app.command("install")
def integrate_install() -> None:
    """Add the SessionStart and SessionEnd hooks (auto-save and notices), and the /cfg-push skill."""
    with reported_errors():
        report = _manager().install()
    settings, skill = escape(str(report.settings_path)), escape(str(report.skill_path))
    if report.hook_changed:
        console.print(
            f"[green]Added the SessionStart hook `{START_HOOK.command}` and the SessionEnd "
            f"hook `{END_HOOK.command}` to {settings}[/green]"
        )
    else:
        console.print(f"The session hooks are already in {settings}")
    if report.skill_found is SkillState.FOREIGN:
        console.print(
            f"[yellow]Left {skill} alone: it was not written by claude-cfg. Move it away "
            "and run this again to install /cfg-push.[/yellow]"
        )
    else:
        console.print(f"[green]Wrote the /cfg-push skill to {skill}[/green]")


@integrate_app.command("remove")
def integrate_remove() -> None:
    """Remove the session hooks and the /cfg-push skill that `integrate install` added."""
    with reported_errors():
        report = _manager().remove()
    settings, skill = escape(str(report.settings_path)), escape(str(report.skill_path))
    hook_line = "Removed the session hooks from" if report.hook_changed else "No claude-cfg hook in"
    console.print(f"{hook_line} {settings}")
    skill_lines = {
        SkillState.OURS: f"Removed the /cfg-push skill at {skill}",
        SkillState.MISSING: "The /cfg-push skill was not installed.",
        SkillState.FOREIGN: f"[yellow]Left {skill} alone: it was not written by claude-cfg.[/yellow]",
    }
    console.print(skill_lines[report.skill_found])


@integrate_app.command("status")
def integrate_status() -> None:
    """Show whether the session hooks and the /cfg-push skill are installed."""
    with reported_errors():
        status = _manager().status()
    hook_state = "installed" if status.hook_installed else "not installed"
    if status.hook_installed and not status.hook_current:
        hook_state += f", an older version. Run `{command_hint('integrate install')}` to update it"
    console.print(f"SessionStart hook: {hook_state} ({escape(str(status.settings_path))})")
    console.print(f"/cfg-push skill: {status.skill.value} ({escape(str(status.skill_path))})")
