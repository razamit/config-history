"""Building the MCP server pieces of push, pull and status from the config.

Everything here returns nothing (or None) when ``mcp_servers.enabled`` is
off, so the callers in :mod:`claude_cfg.core` need no MCP checks of their own.
"""

from pathlib import Path
from typing import Optional

from claude_cfg.command_runner import CommandRunner, SubprocessCommandRunner
from claude_cfg.config import is_mcp_sync_enabled
from claude_cfg.content_hashing import sha256_hex
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.external_members import MCP_SERVERS_MEMBER
from claude_cfg.mcp_server_capture import capture_mcp_servers, read_user_mcp_servers
from claude_cfg.mcp_server_plan import McpServerPlan, McpServerPlanner
from claude_cfg.mcp_server_sync import McpServerSyncManager
from claude_cfg.pull_manager import McpPlanBuilder
from claude_cfg.snapshot_contents import SnapshotContents
from claude_cfg.sync_status import ExternalHasher


def external_members_for_push(
    cfg: dict, claude_json_path: Path, transform: PathTokenTransform
) -> dict[str, bytes]:
    """``{member: stored bytes}`` to add to a new snapshot."""
    if not is_mcp_sync_enabled(cfg):
        return {}
    return {MCP_SERVERS_MEMBER: capture_mcp_servers(claude_json_path, transform)}


def external_hasher_for_status(
    cfg: dict, claude_json_path: Path, transform: PathTokenTransform
) -> Optional[ExternalHasher]:
    if not is_mcp_sync_enabled(cfg):
        return None

    def hash_members() -> dict[str, str]:
        members = external_members_for_push(cfg, claude_json_path, transform)
        return {name: sha256_hex(stored) for name, stored in members.items()}

    return hash_members


def mcp_plan_builder(
    cfg: dict, claude_json_path: Path, transform: PathTokenTransform
) -> Optional[McpPlanBuilder]:
    """Plans the MCP part of a pull. A snapshot without a server list plans
    nothing, so it never removes servers it knows nothing about."""
    if not is_mcp_sync_enabled(cfg):
        return None
    planner = McpServerPlanner(transform)

    def build(contents: SnapshotContents, exact: bool) -> Optional[McpServerPlan]:
        stored = contents.stored_files.get(MCP_SERVERS_MEMBER)
        if stored is None:
            return None
        return planner.plan(stored, read_user_mcp_servers(claude_json_path), exact)

    return build


def build_mcp_manager(runner: Optional[CommandRunner] = None) -> McpServerSyncManager:
    return McpServerSyncManager(runner if runner is not None else SubprocessCommandRunner())
