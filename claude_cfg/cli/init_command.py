"""The ``claude-cfg init`` wizard, one small function per step."""

from typing import Optional

import typer
from rich.markup import escape

from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.cli.backend_prompts import (
    describe_snapshot_destination,
    prompt_backend_choice,
    prompt_backend_settings,
)
from claude_cfg.cli.command_context import prompt_existing_passphrase
from claude_cfg.cli.encryption_prompts import (
    ask_whether_to_encrypt,
    check_passphrase_against_backend,
    encryption_section,
    with_session_passphrase,
)
from claude_cfg.cli.mcp_prompts import ask_whether_to_sync_mcp
from claude_cfg.cli.output import (
    console,
    print_push_result,
    print_snapshot_summary,
)
from claude_cfg.cli.restore_output import print_pull_result
from claude_cfg.config import DEFAULT_TRACKED, ENCRYPTION_KEY, set_mcp_sync_enabled
from claude_cfg.default_history import existing_local_history
from claude_cfg.paths import config_file
from claude_cfg.program_name import command_hint
from claude_cfg.providers import get_provider
from claude_cfg.providers.base import StorageProvider


def init_command() -> None:
    """Choose where versions are stored. Optional: without it, they stay on this machine."""
    console.print(f"[bold]{escape(command_hint('init'))}[/bold]\n")
    _mention_existing_history()
    storage = prompt_backend_choice()
    backend_cfg = prompt_backend_settings(storage)
    new_cfg: dict = {"storage": storage, "tracked": _choose_tracked_files(), storage: backend_cfg}

    provider = _test_connection(new_cfg)
    encryption_choice = ask_whether_to_encrypt()
    if encryption_choice is not None:
        check_passphrase_against_backend(encryption_choice.passphrase, lambda: provider)
        new_cfg[ENCRYPTION_KEY] = encryption_section(encryption_choice)
    set_mcp_sync_enabled(new_cfg, ask_whether_to_sync_mcp(encryption_choice is not None))

    _save_config(new_cfg, provider)
    console.print(f"\n[green]Config saved to {config_file()}[/green]")
    destination = describe_snapshot_destination(storage, backend_cfg)
    console.print(f"[green]Snapshots will be stored in: {destination}[/green]")

    if provider is None:
        console.print(f"Run [bold]{escape(command_hint('push'))}[/bold] once the backend is reachable.")
        return
    _seed_or_restore(with_session_passphrase(new_cfg, encryption_choice), provider)
    if storage == "gist":
        # A new Gist only gets its id on the first upload, so save it now.
        _save_config(new_cfg, provider)


def _mention_existing_history() -> None:
    """Say that the automatic local history stays where it is."""
    try:
        found = existing_local_history(cfg_mod.load())
    except (OSError, ValueError):
        return
    if found is None:
        return
    folder, count = found
    console.print(
        f"A local history with {count} saved version(s) already exists at "
        f"{escape(str(folder))}. It stays in place. The setup below replaces the automatic "
        "config; to keep adding to that history, choose the local backend and enter that "
        "folder.\n"
    )


def _choose_tracked_files() -> list[str]:
    console.print(f"\nDefault tracked files: {', '.join(DEFAULT_TRACKED)}")
    if not typer.confirm("Customize tracked files?", default=False):
        return list(DEFAULT_TRACKED)
    raw = typer.prompt("Enter comma-separated files/folders")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def _test_connection(cfg: dict) -> Optional[StorageProvider]:
    """The provider when the backend answers; None if the user saves anyway."""
    console.print("\nTesting connection...")
    try:
        provider = get_provider(cfg)
        provider.list_keys()
        console.print("[green]Connection successful.[/green]")
        return provider
    except Exception as error:
        console.print(f"[yellow]Warning: connection test failed: {error}[/yellow]")
        if not typer.confirm("Save config anyway?", default=False):
            raise typer.Abort()
        return None


def _save_config(cfg: dict, provider: Optional[StorageProvider]) -> None:
    """Save the config, picking up a Gist id the provider may have just created."""
    gist_id = getattr(provider, "gist_id", "") if cfg["storage"] == "gist" else ""
    if gist_id:
        cfg["gist"]["gist_id"] = gist_id
    cfg_mod.save(cfg)


def _seed_or_restore(cfg: dict, provider: StorageProvider) -> None:
    """Push this machine's config, or pull an existing snapshot onto it.

    On a fresh backend there is nothing to restore, so this just pushes.
    """
    try:
        existing = core.list_snapshots(provider)
    except Exception:
        existing = []
    if existing and _choose_first_action(existing) == "restore":
        _init_restore(cfg, provider)
    else:
        _init_push(cfg, provider)


def _choose_first_action(existing: list[dict]) -> str:
    print_snapshot_summary(existing)
    console.print(
        "\n[bold]push[/bold]    save THIS machine's ~/.claude as a new snapshot\n"
        "[bold]restore[/bold] download an existing snapshot onto THIS machine"
    )
    action = typer.prompt("Choose action (push/restore)", default="restore")
    return "restore" if action.lower().strip().startswith("r") else "push"


def _init_push(cfg: dict, provider: StorageProvider) -> None:
    console.print("\nCreating initial snapshot...")
    try:
        result = core.push("initial", cfg, provider, passphrase_prompt=prompt_existing_passphrase)
    except Exception as error:
        console.print(f"[yellow]Warning: initial snapshot failed: {error}[/yellow]")
        console.print(f"Run [bold]{escape(command_hint('push'))}[/bold] manually when ready.")
        return
    print_push_result(result)


def _init_restore(cfg: dict, provider: StorageProvider) -> None:
    raw = typer.prompt("Snapshot ID to restore (blank = latest)", default="").strip()
    point = int(raw) if raw else None
    console.print("\nRestoring snapshot...")
    try:
        result = core.pull(point, cfg, provider, passphrase_prompt=prompt_existing_passphrase)
    except Exception as error:
        console.print(f"[yellow]Warning: restore failed: {error}[/yellow]")
        console.print(f"Run [bold]{escape(command_hint('pull'))}[/bold] manually when ready.")
        return
    print_pull_result(result)
