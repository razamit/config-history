"""Questions about syncing MCP servers, shared by init and config mcp."""

import typer

from claude_cfg.cli.output import console
from claude_cfg.program_name import command_hint

INIT_QUESTION = "\nSync user-level MCP servers? Their definitions often contain API tokens."


def ask_whether_to_sync_mcp(encryption_enabled: bool) -> bool:
    """The init wizard step. Defaults to yes only when snapshots are encrypted."""
    return typer.confirm(INIT_QUESTION, default=encryption_enabled)


def confirm_unencrypted_mcp_sync() -> bool:
    """An explicit yes before MCP definitions go to the backend in plain text."""
    console.print(
        "[yellow]Encryption is off. MCP server definitions often contain API tokens "
        "and keys, and without encryption they are stored in plain text on the "
        "backend, where anyone with access to it can read them.[/yellow]"
    )
    return typer.confirm("Sync MCP servers without encryption anyway?", default=False)


def print_mcp_sync_state(enabled: bool) -> None:
    if enabled:
        console.print(
            "MCP server sync is on. User-scope servers travel with each push; a pull "
            "applies them with the `claude mcp` command."
        )
    else:
        console.print(
            f"MCP server sync is off. Turn it on with `{command_hint('config mcp --enable')}`."
        )
