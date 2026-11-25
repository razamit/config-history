"""Capturing MCP servers into a snapshot and planning their restore."""

import json

import pytest

from claude_cfg import core
from claude_cfg import snapshot as snap
from claude_cfg.content_hashing import sha256_hex
from claude_cfg.content_transform import PathTokenTransform
from claude_cfg.errors import McpConfigReadError
from claude_cfg.external_members import MCP_SERVERS_MEMBER
from claude_cfg.mcp_server_capture import capture_mcp_servers, read_user_mcp_servers
from claude_cfg.mcp_server_plan import McpServerPlanner
from claude_cfg.paths import claude_dir, claude_json_file, state_file
from claude_cfg.restore_plan import RestorePlanner
from claude_cfg.restore_writer import SafeDeleter
from claude_cfg.snapshot_contents import SnapshotContents
from tests.mcp_fixtures import MCP_CFG, SECRET, remote_server, stdio_server, write_claude_json
from tests.memory_provider import MemoryProvider
from tests.sync_helpers import write_files


@pytest.fixture
def transform():
    return core.this_machine_transform()


@pytest.fixture
def claude_md():
    write_files(claude_dir(), {"CLAUDE.md": "# hi"})


def test_missing_file_means_no_servers():
    assert read_user_mcp_servers(claude_json_file()) == {}


def test_missing_key_means_no_servers():
    write_claude_json(None)
    assert read_user_mcp_servers(claude_json_file()) == {}


def test_invalid_file_raises_without_its_contents():
    claude_json_file().write_text('{"mcpServers": {"x": {"env": {"K": "' + SECRET)
    with pytest.raises(McpConfigReadError) as raised:
        read_user_mcp_servers(claude_json_file())
    assert SECRET not in str(raised.value)


def test_capture_reads_only_user_servers_and_tokenizes_paths(transform):
    write_claude_json({"files": stdio_server(), "web": remote_server()})
    captured = json.loads(capture_mcp_servers(claude_json_file(), transform))
    assert sorted(captured) == ["files", "web"]
    assert captured["files"]["args"] == ["${HOME}/mcp/server.js"]
    assert captured["web"] == remote_server()


def test_push_stores_member_with_hash_in_manifest_and_state(claude_md):
    write_claude_json({"files": stdio_server()})
    provider = MemoryProvider()
    core.push("m", MCP_CFG, provider)
    zip_bytes = next(v for k, v in provider._store.items() if k.startswith("snapshots/"))
    member = SnapshotContents.from_zip(zip_bytes).stored_files[MCP_SERVERS_MEMBER]
    manifest = snap.read_manifest(zip_bytes)
    assert manifest["file_hashes"][MCP_SERVERS_MEMBER] == sha256_hex(member)
    state = json.loads(state_file().read_text())
    assert state["file_hashes"][MCP_SERVERS_MEMBER] == sha256_hex(member)


def test_push_without_opt_in_has_no_member(claude_md):
    write_claude_json({"files": stdio_server()})
    provider = MemoryProvider()
    core.push("m", {**MCP_CFG, "mcp_servers": {"enabled": False}}, provider)
    zip_bytes = next(v for k, v in provider._store.items() if k.startswith("snapshots/"))
    assert MCP_SERVERS_MEMBER not in SnapshotContents.from_zip(zip_bytes).stored_files


def _stored(servers: dict, transform: PathTokenTransform) -> bytes:
    write_claude_json(servers)
    return capture_mcp_servers(claude_json_file(), transform)


def test_plan_covers_add_replace_unchanged_and_local_only(transform):
    stored = _stored({"same": stdio_server(), "changed": remote_server("https://new"), "new": stdio_server("n.js")}, transform)
    local = {"same": stdio_server(), "changed": remote_server("https://old"), "mine": remote_server()}
    plan = McpServerPlanner(transform).plan(stored, local, exact=False)
    assert (plan.to_add, plan.to_replace, plan.unchanged) == (["new"], ["changed"], ["same"])
    assert plan.only_local == ["mine"] and plan.to_remove == []
    assert plan.previous_definitions == {"changed": remote_server("https://old")}
    assert SECRET not in repr(plan)


def test_exact_plan_removes_local_only_servers(transform):
    stored = _stored({"same": stdio_server()}, transform)
    plan = McpServerPlanner(transform).plan(stored, {"same": stdio_server(), "mine": remote_server()}, exact=True)
    assert plan.to_remove == ["mine"]
    assert plan.previous_definitions == {"mine": remote_server()}


def test_server_differing_only_by_home_is_unchanged(tmp_path):
    source = PathTokenTransform(home=tmp_path / "a", sep="/", python="python3")
    target = PathTokenTransform(home=tmp_path / "b", sep="/", python="python3")
    definition = {"command": "node", "args": [f"{tmp_path}/a/s.js"]}
    stored = source.to_stored(MCP_SERVERS_MEMBER, json.dumps({"s": definition}).encode())
    moved = {"command": "node", "args": [f"{tmp_path}/b/s.js"]}
    plan = McpServerPlanner(target).plan(stored, {"s": moved}, exact=True)
    assert plan.unchanged == ["s"] and not plan.has_changes


def test_file_planner_and_exact_delete_ignore_external_prefix(tmp_path, transform):
    target = tmp_path / ".claude"
    write_files(target, {"_external/mcp-servers.json": "local copy", "skills/a.md": "a"})
    contents = SnapshotContents(
        manifest={"tracked": ["skills/", "_external/"]},
        stored_files={MCP_SERVERS_MEMBER: b"{}", "skills/a.md": b"a"},
    )
    plan = RestorePlanner(transform).plan(contents, target, ["skills/", "_external/"], exact=True)
    every_listed = plan.to_create + plan.to_overwrite + plan.unchanged + plan.to_delete + plan.only_local
    assert not any(path.startswith("_external/") for path in every_listed)
    assert not SafeDeleter(target, ["_external"]).may_delete(MCP_SERVERS_MEMBER)
    assert (target / "_external/mcp-servers.json").read_text() == "local copy"


def test_status_sees_mcp_changes_only_when_enabled(claude_md):
    write_claude_json({"files": stdio_server()})
    core.push("m", MCP_CFG, MemoryProvider())
    assert not core.status(MCP_CFG).local_changes.has_changes

    write_claude_json({"files": stdio_server(key="rotated")})
    assert core.status(MCP_CFG).local_changes.modified == [MCP_SERVERS_MEMBER]
    disabled = {**MCP_CFG, "mcp_servers": {"enabled": False}}
    assert not core.status(disabled).local_changes.has_changes


def test_plain_extraction_skips_external_members(tmp_path):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MCP_SERVERS_MEMBER, "{}")
        archive.writestr("CLAUDE.md", "# hi")
        archive.writestr(snap.MANIFEST_NAME, "{}")
    assert snap.extract_zip(buffer.getvalue(), tmp_path / "out") == ["CLAUDE.md"]
    assert not (tmp_path / "out" / "_external").exists()
