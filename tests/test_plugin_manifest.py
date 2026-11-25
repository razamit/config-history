"""Checks for the config-history plugin packaging files.

Covers the plugin manifest, the marketplace file, hooks/hooks.json and the
skill files. Reads files only.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
HOOKS_FILE = REPO_ROOT / "hooks" / "hooks.json"
SKILLS_DIR = REPO_ROOT / "skills"
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"

RESERVED_PLUGIN_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
EXPECTED_SKILLS = {"history", "restore", "undo"}
SKILLS_WITH_ARGUMENTS = {"history", "restore"}
# The one skill Claude may start by itself; the others run only when typed.
MODEL_INVOKED_SKILLS = {"history"}
ALLOWED_TOOL_PATTERN = re.compile(r"^Bash\(config-history [a-z]+( \*| --dry-run --point \*)?\)$")
# Skills that change files: none of their pre-approved commands may do so.
SKILLS_THAT_CHANGE_FILES = {"restore", "undo"}
# Subcommands that never change or delete a file in the Claude config.
# ``save`` only adds a version to the history.
READ_ONLY_SUBCOMMANDS = {"history", "list", "diff", "status", "save"}
KEBAB_CASE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EM_DASH = chr(0x2014)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_has_required_fields():
    manifest = load_json(PLUGIN_MANIFEST)
    assert manifest["name"] == "config-history"
    assert KEBAB_CASE.match(manifest["name"])
    assert manifest["version"] == "0.3.0"
    assert manifest["description"].strip()
    assert manifest["author"]["name"] == "Amit Razam"
    assert manifest["homepage"] == "https://github.com/razamit/config-history"
    assert manifest["repository"] == "https://github.com/razamit/config-history"
    assert manifest["license"] == "MIT"
    assert manifest["keywords"] and all(isinstance(word, str) for word in manifest["keywords"])


def test_plugin_name_is_not_reserved():
    name = load_json(PLUGIN_MANIFEST)["name"].lower()
    assert not name.startswith(RESERVED_PLUGIN_PREFIXES)
    assert "claude" not in name.split("-")
    assert "anthropic" not in name.split("-")


def test_only_manifest_and_marketplace_live_in_claude_plugin_dir():
    names = {entry.name for entry in (REPO_ROOT / ".claude-plugin").iterdir()}
    assert names == {"plugin.json", "marketplace.json"}


def test_marketplace_lists_the_plugin_at_repo_root():
    marketplace = load_json(MARKETPLACE_FILE)
    assert marketplace["name"] == "razamit"
    assert marketplace["owner"]["name"].strip()
    assert len(marketplace["plugins"]) == 1
    entry = marketplace["plugins"][0]
    assert entry["source"] == "./"
    assert entry["name"] == load_json(PLUGIN_MANIFEST)["name"]
    assert "version" not in entry, "plugin.json carries the version; a second copy would drift"


def test_hooks_file_shape():
    hooks = load_json(HOOKS_FILE)["hooks"]
    assert set(hooks) == {"SessionStart", "SessionEnd"}
    start_group = hooks["SessionStart"][0]
    assert start_group["matcher"] == "startup"
    start_hook = start_group["hooks"][0]
    end_hook = hooks["SessionEnd"][0]["hooks"][0]
    assert start_hook["type"] == end_hook["type"] == "command"
    assert start_hook["timeout"] == 15
    assert end_hook["timeout"] == 30
    assert start_hook["command"].endswith(" start")
    assert end_hook["command"].endswith(" end")


@pytest.mark.parametrize("event", ["SessionStart", "SessionEnd"])
def test_hook_command_quotes_plugin_root_and_names_an_existing_script(event):
    command = load_json(HOOKS_FILE)["hooks"][event][0]["hooks"][0]["command"]
    match = re.match(r'^sh "\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)" (start|end)$', command)
    assert match, command
    assert (REPO_ROOT / match.group(1)).is_file()


def test_plugin_version_matches_package_version_pending_bump():
    """PENDING: fails until pyproject.toml is bumped to the plugin version (0.3.0).

    The plugin and the Python package ship from the same repo, so their
    versions must move together.
    """
    package_version = re.search(
        r'^version\s*=\s*"([^"]+)"', PYPROJECT_FILE.read_text(encoding="utf-8"), re.MULTILINE
    ).group(1)
    plugin_version = load_json(PLUGIN_MANIFEST)["version"]
    assert plugin_version == package_version, (
        "plugin.json version {} differs from pyproject.toml version {}".format(
            plugin_version, package_version)
    )


def parse_frontmatter(skill_file: Path) -> dict:
    """Parse the simple YAML frontmatter used by the skills: scalars and lists."""
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", skill_file
    closing = lines.index("---", 1)
    fields, current_list = {}, None
    for line in lines[1:closing]:
        if line.startswith("  - ") and current_list is not None:
            current_list.append(line[4:].strip())
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"')
        current_list = [] if value == "" else None
        fields[key.strip()] = current_list if value == "" else value
    return fields


def test_expected_skills_exist():
    found = {path.parent.name for path in SKILLS_DIR.glob("*/SKILL.md")}
    assert found == EXPECTED_SKILLS


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_skill_frontmatter(skill_name):
    fields = parse_frontmatter(SKILLS_DIR / skill_name / "SKILL.md")
    assert fields["name"] == skill_name
    assert fields["description"].strip()
    if skill_name in MODEL_INVOKED_SKILLS:
        assert "disable-model-invocation" not in fields
    else:
        assert fields["disable-model-invocation"] == "true"
    if skill_name in SKILLS_WITH_ARGUMENTS:
        assert fields["argument-hint"].strip()
    tools = fields.get("allowed-tools", [])
    assert isinstance(tools, list)
    assert bool(tools) == (skill_name != "undo")
    for tool in tools:
        assert ALLOWED_TOOL_PATTERN.match(tool), tool


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_skill_only_allows_commands_it_mentions(skill_name):
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    body = skill_file.read_text(encoding="utf-8").split("---", 2)[2]
    for tool in parse_frontmatter(skill_file).get("allowed-tools", []):
        subcommand = tool[len("Bash(config-history "):].split(" ")[0].rstrip(")")
        assert "config-history " + subcommand in body


def test_only_history_may_be_invoked_by_claude():
    invocable = {
        path.parent.name
        for path in SKILLS_DIR.glob("*/SKILL.md")
        if parse_frontmatter(path).get("disable-model-invocation") != "true"
    }
    assert invocable == MODEL_INVOKED_SKILLS


def skill_body(skill_name: str) -> str:
    return (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]


def test_history_skill_pre_approves_nothing_that_changes_or_deletes_files():
    skill_file = SKILLS_DIR / "history" / "SKILL.md"
    tools = parse_frontmatter(skill_file)["allowed-tools"]
    assert tools == [
        "Bash(config-history history)",
        "Bash(config-history list)",
        "Bash(config-history diff)",
        "Bash(config-history status)",
        "Bash(config-history save)",
    ]
    subcommands = {tool[len("Bash(config-history "):].rstrip(")") for tool in tools}
    assert subcommands <= READ_ONLY_SUBCOMMANDS
    body = skill_body("history")
    assert "/config-history:restore" in body, "points the user to the restore skill"
    assert "config-history save -- '<label>'" in body


@pytest.mark.parametrize("character", ["*", "$", "`", ";", "&", "|"])
def test_history_skill_allow_rules_are_exact_commands(character):
    """Claude may start this skill by itself, so its rules match one exact
    command each: no wildcard, and nothing a shell would expand or chain."""
    for tool in parse_frontmatter(SKILLS_DIR / "history" / "SKILL.md")["allowed-tools"]:
        assert character not in tool, tool


def test_history_skill_says_arguments_ask_for_permission():
    body = skill_body("history")
    assert "with nothing after them" in body
    assert "such as `--limit`, `--point` or a save label, makes Claude Code ask the user " \
           "for permission first" in body


def test_history_description_stays_short_and_scoped_to_claude_code():
    """It is in Claude's context in every session, so it stays short and
    fires only for Claude Code's own config, not for any app's settings."""
    description = parse_frontmatter(SKILLS_DIR / "history" / "SKILL.md")["description"]
    assert len(description) <= 250, len(description)
    for topic in ("Claude Code config in ~/.claude", "settings", "hooks", "skills", "agents",
                  "commands", "MCP servers", "CLAUDE.md", "changed", "versions"):
        assert topic in description
    assert "stopped working after a config change" not in description
    assert "Claude Code misbehaves after a change to it" in description


def test_restore_skill_walks_through_the_flow():
    body = skill_body("restore")
    steps = ["config-history history", "config-history restore --dry-run --point N",
             "--only", "Restore this version now?", "config-history restore --point N`",
             "restart Claude Code", "/config-history:undo"]
    positions = [body.index(step) for step in steps]
    assert positions == sorted(positions), "the steps are in order"
    assert "Never add `--exact` unless the user asked" in body


def test_restore_skill_confirms_in_the_conversation_before_restoring():
    """The permission prompt can be off (bypass or auto mode, or "don't ask
    again"), so the skill itself must show the plan and wait for a yes."""
    body = skill_body("restore")
    for phrase in (
        "This step is required every time, even when the user named the version",
        "Show the chosen version: its number, when it was saved, and its label or what changed.",
        "Show the list of files that will change, from the last dry run.",
        'Ask: "Restore this version now?" Then stop and wait for the answer.',
        "Go on only after a clear yes. A vague answer, another question, or no answer means "
        "no restore",
        "Claude Code's permission prompt for the restore is a second check, never a "
        "replacement for this confirmation.",
    ):
        assert phrase in body, phrase
    assert body.index("Restore this version now?") < body.index("Everything: `config-history restore")


def test_restore_skill_only_pre_approves_a_dry_run_with_the_flag_first():
    """``--dry-run`` comes first, so no ``--only`` value can swallow it."""
    tools = parse_frontmatter(SKILLS_DIR / "restore" / "SKILL.md")["allowed-tools"]
    restore_rules = [tool for tool in tools if tool.startswith("Bash(config-history restore")]
    assert restore_rules == ["Bash(config-history restore --dry-run --point *)"]


def test_restore_skill_previews_with_the_dry_run_flag_first():
    previews = re.findall(r"config-history restore [^`]*--dry-run", skill_body("restore"))
    assert len(previews) >= 3
    for preview in previews:
        assert preview.startswith("config-history restore --dry-run"), preview


# What each skill that changes files must say about the permission prompt.
PERMISSION_PHRASES = {
    "restore": "Claude Code's permission prompt for the restore is a second check",
    "undo": "so it is not pre-approved: Claude Code asks the user for permission before it runs",
}


@pytest.mark.parametrize("skill_name", sorted(SKILLS_THAT_CHANGE_FILES))
def test_skills_that_change_files_pre_approve_only_read_only_commands(skill_name):
    """A real restore or undo must go through Claude Code's permission prompt."""
    tools = parse_frontmatter(SKILLS_DIR / skill_name / "SKILL.md").get("allowed-tools", [])
    for tool in tools:
        subcommand = tool[len("Bash(config-history "):].split(" ")[0].rstrip(")")
        is_dry_run = tool.startswith("Bash(config-history restore --dry-run ")
        assert subcommand in {"history", "diff"} or is_dry_run, tool
        assert "undo" not in tool and "--yes" not in tool and "--exact" not in tool
        assert "save" not in tool and "status" not in tool
    assert PERMISSION_PHRASES[skill_name] in skill_body(skill_name)


def test_undo_skill_pre_approves_nothing():
    assert "allowed-tools" not in parse_frontmatter(SKILLS_DIR / "undo" / "SKILL.md")


def plugin_files():
    roots = [REPO_ROOT / ".claude-plugin", REPO_ROOT / "hooks", REPO_ROOT / "bin",
             REPO_ROOT / "scripts", SKILLS_DIR]
    files = [path for root in roots for path in root.rglob("*") if path.is_file()]
    files += sorted((REPO_ROOT / "tests").glob("test_plugin_*.py"))
    return [path for path in files if "__pycache__" not in path.parts]


def test_plugin_files_contain_no_em_dash():
    offenders = [str(path) for path in plugin_files() if EM_DASH in path.read_text(encoding="utf-8")]
    assert offenders == []


CONSTRAINTS_FILE = REPO_ROOT / "scripts" / "plugin-constraints.txt"


def runtime_dependency_names():
    text = PYPROJECT_FILE.read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)\]", text, re.MULTILINE | re.DOTALL).group(1)
    return [re.match(r"[A-Za-z0-9_.-]+", item).group(0).lower()
            for item in re.findall(r'"([^"]+)"', block)]


def test_runtime_dependencies_drop_the_removed_typer_extra():
    assert "typer[all]" not in PYPROJECT_FILE.read_text(encoding="utf-8")


def test_constraints_pin_every_runtime_dependency_exactly():
    pins = {}
    for line in CONSTRAINTS_FILE.read_text(encoding="utf-8").splitlines():
        requirement = line.split("#", 1)[0].strip()
        if requirement:
            name, _, version = requirement.split(";")[0].strip().partition("==")
            assert version.strip(), "not an exact pin: " + line
            pins.setdefault(name.lower(), []).append(line)
    for name in runtime_dependency_names() + ["click"]:
        assert name in pins, name + " is not pinned"
    assert "maintained with each release" in CONSTRAINTS_FILE.read_text(encoding="utf-8").lower()


def test_manifest_declares_the_package_index_hosts():
    hosts = load_json(PLUGIN_MANIFEST)["network"]["hosts"]
    assert set(hosts) == {"pypi.org", "files.pythonhosted.org"}
