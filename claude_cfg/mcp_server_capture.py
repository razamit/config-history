"""Reading user-scope MCP servers and converting them to and from stored form.

Claude Code keeps user-scope servers in the top-level ``mcpServers`` object of
``.claude.json``. That file is only ever read here; changes go through the
``claude mcp`` CLI (see :mod:`claude_cfg.mcp_server_sync`). Error messages
never include file contents, because definitions often hold tokens.
"""

import json
from pathlib import Path

from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.errors import McpConfigReadError
from claude_cfg.external_members import MCP_SERVERS_MEMBER

MCP_SERVERS_FIELD = "mcpServers"

McpServers = dict[str, dict]


def read_user_mcp_servers(claude_json_path: Path) -> McpServers:
    """User-scope servers by name. A missing file or key means none.

    A file that exists but is not valid JSON raises instead of reading as
    empty, so an exact pull can never mistake it for "no servers".
    """
    try:
        text = claude_json_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise McpConfigReadError(
            f"Could not read {claude_json_path} ({type(error).__name__})."
        ) from None
    try:
        document = json.loads(text)
    except ValueError:
        raise McpConfigReadError(f"{claude_json_path} is not valid JSON.") from None
    servers = document.get(MCP_SERVERS_FIELD) if isinstance(document, dict) else None
    return _only_definitions(servers)


def _only_definitions(servers: object) -> McpServers:
    if not isinstance(servers, dict):
        return {}
    return {str(name): definition for name, definition in servers.items() if isinstance(definition, dict)}


def serialize_servers(servers: McpServers) -> bytes:
    """Stable bytes for a server map, so equal maps always hash the same."""
    return json.dumps(servers, indent=2, sort_keys=True).encode("utf-8")


def capture_mcp_servers(claude_json_path: Path, transform: PathTokenTransform) -> bytes:
    """The ``_external/mcp-servers.json`` member: servers with paths tokenized."""
    servers = read_user_mcp_servers(claude_json_path)
    return transform.to_stored(MCP_SERVERS_MEMBER, serialize_servers(servers))


def parse_stored_servers(stored: bytes, transform: PathTokenTransform) -> McpServers:
    """A snapshot's server map with tokens expanded for this machine."""
    return _parse_member(transform.to_local(MCP_SERVERS_MEMBER, stored))


def parse_tokenized_servers(stored: bytes) -> McpServers:
    """A snapshot's server map as stored, tokens left in place."""
    return _parse_member(stored)


def tokenize_definition(definition: dict, transform: PathTokenTransform) -> dict:
    """One local definition in the form a push would store it."""
    stored = transform.to_stored(MCP_SERVERS_MEMBER, json.dumps(definition).encode("utf-8"))
    return json.loads(stored)


def _parse_member(member_bytes: bytes) -> McpServers:
    try:
        document = json.loads(member_bytes)
    except ValueError:
        raise McpConfigReadError("The snapshot's MCP server list is not valid JSON.") from None
    if not isinstance(document, dict):
        raise McpConfigReadError("The snapshot's MCP server list has an unexpected shape.")
    return _only_definitions(document)
