"""The plain dict a finished pull is described with, for the CLI and callers.

Only file paths, counts and MCP server names go in, never file contents or
server definitions.
"""

import socket
from typing import Optional

from claude_cfg.paths import Target, normalize_platform_name
from claude_cfg.pull_manager import PullOutcome


def is_from_other_machine(manifest: dict, this_machine: str) -> bool:
    """True unless the snapshot names this machine. A missing name counts as other."""
    source = manifest.get("machine")
    return not (isinstance(source, str) and source and source == this_machine)


def describe_pull(
    outcome: PullOutcome,
    target: Target,
    session_hook_removed: bool = False,
    this_machine: Optional[str] = None,
) -> dict:
    prepared, plan, applied = outcome.prepared, outcome.prepared.plan, outcome.applied
    entry, manifest = prepared.entry, prepared.contents.manifest
    machine = this_machine if this_machine is not None else socket.gethostname()
    return {
        "id": entry.snapshot_id,
        "timestamp": entry.timestamp,
        "key": entry.key,
        "message": manifest.get("message", entry.message),
        "automatic": entry.automatic,
        "encrypted": prepared.encrypted,
        "files_restored": len(applied.written),
        "created": len(plan.to_create),
        "overwritten": len(plan.to_overwrite),
        "deleted": len(applied.deleted),
        "unchanged": len(plan.unchanged),
        "kept_local": 0 if plan.exact else len(plan.only_local),
        "refused_deletes": list(applied.refused_deletes),
        "left_untouched": dict(plan.left_untouched),
        "backup_dir": str(outcome.backup.path) if outcome.backup else None,
        "backups_pruned": len(outcome.pruned),
        "source_platform": normalize_platform_name(manifest.get("source_platform", "unknown")),
        "target_platform": target.platform,
        "python_launcher": target.python,
        "is_wsl": target.is_wsl,
        "from_other_machine": is_from_other_machine(manifest, machine),
        "mcp": describe_mcp(outcome),
        "session_hook_removed": session_hook_removed,
        "only_paths": list(plan.only_paths),
    }


def describe_mcp(outcome: PullOutcome) -> Optional[dict]:
    """Server names only, never definitions. None when MCP was not planned."""
    mcp_plan = outcome.prepared.mcp_plan
    if mcp_plan is None:
        return None
    result = outcome.mcp_result
    return {
        "added": list(mcp_plan.to_add),
        "replaced": list(mcp_plan.to_replace),
        "removed": list(mcp_plan.to_remove),
        "unchanged": len(mcp_plan.unchanged),
        "kept_local": 0 if mcp_plan.exact else len(mcp_plan.only_local),
        "failed": dict(result.failed) if result else {},
        "rolled_back": list(result.rolled_back) if result else [],
        "skipped_reason": result.skipped_reason if result else None,
    }
