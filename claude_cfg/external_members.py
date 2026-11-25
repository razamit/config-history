"""Snapshot members that do not live inside the Claude folder.

They are stored under ``_external/`` in the archive. The file-based restore
code (planner, writer, backups, exact delete) never touches them; each has
its own manager instead, such as the MCP server sync.
"""

EXTERNAL_FOLDER = "_external"
EXTERNAL_PREFIX = EXTERNAL_FOLDER + "/"
MCP_SERVERS_MEMBER = EXTERNAL_PREFIX + "mcp-servers.json"


def is_external_member(relative_path: str) -> bool:
    """True for an ``_external/`` member, in either separator style."""
    return relative_path.replace("\\", "/").startswith(EXTERNAL_PREFIX)
