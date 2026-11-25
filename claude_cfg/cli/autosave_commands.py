"""The ``autosave`` command and ``config autosave``."""

from typing import Optional

import typer

from claude_cfg import config as cfg_mod
from claude_cfg.autosave_manager import AutoSaveOutcome, AutoSaveResult
from claude_cfg.autosave_message import count_text, file_list_text
from claude_cfg.autosave_setup import build_autosave_manager
from claude_cfg.cli.command_context import load_config_or_exit
from claude_cfg.config import autosave_keep_count, is_autosave_enabled
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.command_wording import CommandWording, wording_for
from claude_cfg.program_name import (
    ask_claude_text,
    command_hint,
    terminal_command_text,
    uses_slash_commands,
)
from claude_cfg.providers import get_provider


def autosave_summary(result: AutoSaveResult, wording: Optional[CommandWording] = None) -> str:
    """One line saying what an auto-save did."""
    outcome = result.outcome
    if outcome is AutoSaveOutcome.SAVED:
        return _saved_summary(result, wording or wording_for(None))
    if outcome is AutoSaveOutcome.NO_CHANGES:
        return "Nothing changed since the last saved version, so nothing was saved."
    if outcome is AutoSaveOutcome.LOCKED:
        return "Skipped: another auto-save is running right now."
    if outcome is AutoSaveOutcome.NO_PASSPHRASE:
        return (
            "Skipped: encryption is on and no passphrase is available without a prompt. "
            f"Set {PASSPHRASE_ENV_VAR}, or run {terminal_command_text('save')} to type it."
        )
    return f"Auto-save failed: {result.reason}"


def _saved_summary(result: AutoSaveResult, wording: CommandWording) -> str:
    if result.first_version:
        text = f"Saved version {result.snapshot_id}, the first version of your settings."
    else:
        changed = result.changed_paths
        text = (
            f"Saved version {result.snapshot_id} "
            f"({count_text(len(changed))} changed: {file_list_text(changed)})."
        )
    if result.pruned_count:
        noun = "version" if result.pruned_count == 1 else "versions"
        text += f" Removed {result.pruned_count} older automatic {noun}."
    if result.previous_id is not None and not result.first_version:
        text += f" {wording.go_back_text(result.previous_id)}"
    return text


def autosave_command() -> None:
    """Save a new version now if anything changed since the last one. Never prompts."""
    cfg = load_config_or_exit()
    result = build_autosave_manager(cfg, provider_factory=lambda c: get_provider(c)).run()
    typer.echo(autosave_summary(result, wording_for(cfg)))
    if result.outcome is AutoSaveOutcome.FAILED:
        raise typer.Exit(1)


def autosave_state_text(cfg: dict) -> str:
    if not is_autosave_enabled(cfg):
        if uses_slash_commands():
            return "Auto-save is off. " + ask_claude_text("config autosave --enable", "turn it on")
        return (
            "Auto-save is off. Turn it on with "
            f"`{command_hint('config autosave --enable')}`."
        )
    return (
        "Auto-save is on. It saves a version when a Claude Code session starts or ends "
        f"and something changed, and keeps the newest {autosave_keep_count(cfg)} automatic "
        "versions. Versions you save yourself are never removed."
    )


def config_autosave_command(
    enable: Optional[bool] = typer.Option(
        None, "--enable/--disable", help="Turn automatic saving on or off."
    ),
    keep: Optional[int] = typer.Option(
        None, "--keep", min=1, help="How many automatic versions to keep."
    ),
) -> None:
    """Show, enable or disable auto-save, and set how many automatic versions to keep."""
    cfg = load_config_or_exit()
    if enable is not None:
        cfg_mod.set_autosave_enabled(cfg, enable)
    if keep is not None:
        cfg_mod.set_autosave_keep(cfg, keep)
    if enable is not None or keep is not None:
        cfg_mod.save(cfg)
    typer.echo(autosave_state_text(cfg))
