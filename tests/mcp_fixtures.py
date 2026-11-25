"""Shared MCP server fixtures. The sentinel token must never reach any output."""

import json

from claude_cfg.paths import claude_json_file, home_dir

SECRET = "sk-SENTINEL-TOKEN-0451"
MCP_CFG = {"storage": "local", "tracked": ["CLAUDE.md"], "mcp_servers": {"enabled": True}}


def stdio_server(script: str = "server.js", key: str = SECRET) -> dict:
    return {
        "type": "stdio",
        "command": "node",
        "args": [f"{home_dir()}/mcp/{script}"],
        "env": {"API_KEY": key},
    }


def remote_server(url: str = "https://mcp.example.com") -> dict:
    return {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {SECRET}"}}


def write_claude_json(servers: dict, **other_keys) -> None:
    """Simulate Claude Code's own file. Only tests write it; claude-cfg never does."""
    document = {"numStartups": 3, "projects": {"/x": {"mcpServers": {"local-only": {}}}}, **other_keys}
    if servers is not None:
        document["mcpServers"] = servers
    claude_json_file().write_text(json.dumps(document))
