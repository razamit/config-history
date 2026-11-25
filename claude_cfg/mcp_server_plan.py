"""Deciding what restoring a snapshot's MCP servers would change.

Only server names are meant for display. The definitions a plan carries are
kept out of its ``repr`` because they often hold tokens.
"""

from dataclasses import dataclass, field

from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.mcp_server_capture import (
    McpServers,
    parse_stored_servers,
    parse_tokenized_servers,
    tokenize_definition,
)


@dataclass(frozen=True)
class McpServerPlan:
    """Per server name: add, replace, unchanged, and remove when exact.

    ``definitions`` holds the native definition for every add and replace.
    ``previous_definitions`` holds the local definition of every server the
    plan replaces or removes, so the change can be undone.
    """

    exact: bool
    to_add: list[str] = field(default_factory=list)
    to_replace: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    only_local: list[str] = field(default_factory=list)
    to_remove: list[str] = field(default_factory=list)
    definitions: McpServers = field(default_factory=dict, repr=False)
    previous_definitions: McpServers = field(default_factory=dict, repr=False)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_add or self.to_replace or self.to_remove)


class McpServerPlanner:
    """Compares a snapshot's server map with the servers on this machine."""

    def __init__(self, transform: PathTokenTransform) -> None:
        self._transform = transform

    def plan(self, stored_member: bytes, local_servers: McpServers, exact: bool) -> McpServerPlan:
        native = parse_stored_servers(stored_member, self._transform)
        tokenized = parse_tokenized_servers(stored_member)
        plan = McpServerPlan(exact=exact)
        for name in sorted(native):
            self._classify(plan, name, native[name], tokenized.get(name), local_servers.get(name))
        plan.only_local.extend(sorted(name for name in local_servers if name not in native))
        if exact:
            plan.to_remove.extend(plan.only_local)
            for name in plan.to_remove:
                plan.previous_definitions[name] = local_servers[name]
        return plan

    def _classify(
        self,
        plan: McpServerPlan,
        name: str,
        native: dict,
        tokenized: object,
        local: object,
    ) -> None:
        if local is None:
            plan.to_add.append(name)
            plan.definitions[name] = native
        elif local == native or tokenize_definition(local, self._transform) == tokenized:
            plan.unchanged.append(name)
        else:
            plan.to_replace.append(name)
            plan.definitions[name] = native
            plan.previous_definitions[name] = local
