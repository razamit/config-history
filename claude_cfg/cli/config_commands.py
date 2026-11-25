"""The ``claude-cfg config`` sub-commands."""

import json
from typing import Optional

import typer
from rich.markup import escape

from claude_cfg import config as cfg_mod
from claude_cfg.cli.command_context import load_config_or_exit
from claude_cfg.cli.encryption_prompts import (
    check_passphrase_against_backend,
    encryption_section,
    prompt_encryption_choice,
)
from claude_cfg.cli.mcp_prompts import confirm_unencrypted_mcp_sync, print_mcp_sync_state
from claude_cfg.cli.output import console
from claude_cfg.config import (
    ENCRYPTION_KEY,
    is_encryption_enabled,
    is_mcp_sync_enabled,
    set_mcp_sync_enabled,
)
from claude_cfg.providers import get_provider
from claude_cfg.tracked_defaults import merge_missing_defaults

config_app = typer.Typer(help="Manage configuration.", pretty_exceptions_show_locals=False)


@config_app.command("show")
def config_show() -> None:
    """Print current config (credentials masked)."""
    cfg = load_config_or_exit()
    console.print_json(json.dumps(cfg_mod.masked(cfg), indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-separated key, e.g. r2.bucket"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a config value."""
    cfg_mod.set_value(key, value)
    leaf = key.rsplit(".", 1)[-1]
    shown = "***" if cfg_mod.is_masked_key(leaf) else value
    console.print(f"[green]Set {key} = {shown}[/green]")


@config_app.command("encrypt")
def config_encrypt() -> None:
    """Turn on passphrase encryption for future pushes."""
    cfg = load_config_or_exit()
    already_on = is_encryption_enabled(cfg)
    if already_on:
        console.print(
            "Encryption is already on. Snapshots pushed with the current "
            "passphrase will still need it to be pulled."
        )
        if not typer.confirm("Set a new passphrase for future pushes?", default=False):
            return
    choice = prompt_encryption_choice()
    check_passphrase_against_backend(
        choice.passphrase, lambda: get_provider(cfg), allow_new_passphrase=already_on
    )
    cfg[ENCRYPTION_KEY] = encryption_section(choice)
    cfg_mod.save(cfg)
    console.print(
        "[green]Encryption is on. New pushes will be encrypted; existing "
        "snapshots stay as they are.[/green]"
    )
    if not choice.save_passphrase:
        console.print(
            "[dim]The passphrase was not saved. Push and pull will ask for it, "
            "or read it from CLAUDE_CFG_PASSPHRASE.[/dim]"
        )


@config_app.command("track-defaults")
def config_track_defaults() -> None:
    """Add any default tracked entries that the saved tracked list is missing."""
    cfg = load_config_or_exit()
    merged, added = merge_missing_defaults(cfg.get("tracked", []))
    if not added:
        console.print("The tracked list already has every default entry.")
        return
    cfg["tracked"] = merged
    cfg_mod.save(cfg)
    console.print(f"[green]Added to the tracked list: {escape(', '.join(added))}[/green]")


@config_app.command("mcp")
def config_mcp(
    enable: Optional[bool] = typer.Option(
        None, "--enable/--disable", help="Turn syncing of user-scope MCP servers on or off."
    ),
) -> None:
    """Show, enable or disable syncing of user-scope MCP servers."""
    cfg = load_config_or_exit()
    if enable is None:
        print_mcp_sync_state(is_mcp_sync_enabled(cfg))
        return
    if enable and not is_encryption_enabled(cfg) and not confirm_unencrypted_mcp_sync():
        console.print("MCP server sync stays off.")
        raise typer.Exit(1)
    set_mcp_sync_enabled(cfg, enable)
    cfg_mod.save(cfg)
    print_mcp_sync_state(enable)
