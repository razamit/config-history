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
EXPECTED_SKILLS = {"save", "history", "diff", "restore", "undo", "status"}
SKILLS_WITH_ARGUMENTS = {"save", "diff", "restore"}
ALLOWED_TOOL_PATTERN = re.compile(r"^Bash\(config-history [a-z]+( \*| --point \* --dry-run)?\)$")
# Skills that change files: none of their pre-approved commands may do so.
SKILLS_THAT_CHANGE_FILES = {"restore", "undo"}
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
    assert manifest["homepage"] == "https://github.com/razamit/claude-cfg"
    assert manifest["repository"] == "https://github.com/razamit/claude-cfg"
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
    assert fields["disable-model-invocation"] == "true"
    if skill_name in SKILLS_WITH_ARGUMENTS:
        assert fields["argument-hint"].strip()
    tools = fields.get("allowed-tools", [])
    assert isinstance(tools, list)
    assert tools or skill_name == "undo"
    for tool in tools:
        assert ALLOWED_TOOL_PATTERN.match(tool), tool


@pytest.mark.parametrize("skill_name", sorted(EXPECTED_SKILLS))
def test_skill_only_allows_commands_it_mentions(skill_name):
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    body = skill_file.read_text(encoding="utf-8").split("---", 2)[2]
    for tool in parse_frontmatter(skill_file).get("allowed-tools", []):
        subcommand = tool[len("Bash(config-history "):].split(" ")[0].rstrip(")")
        assert "config-history " + subcommand in body


def test_restore_skill_confirms_before_restoring():
    body = (SKILLS_DIR / "restore" / "SKILL.md").read_text(encoding="utf-8")
    assert body.index("--dry-run") < body.index("--point N --yes")
    assert "confirm" in body
    assert "config-history undo" in body
    assert "restart Claude Code" in body


@pytest.mark.parametrize("skill_name", sorted(SKILLS_THAT_CHANGE_FILES))
def test_skills_that_change_files_pre_approve_only_read_only_commands(skill_name):
    """A real restore or undo must go through Claude Code's permission prompt."""
    tools = parse_frontmatter(SKILLS_DIR / skill_name / "SKILL.md").get("allowed-tools", [])
    for tool in tools:
        assert tool == "Bash(config-history list)" or tool.endswith(" --dry-run)"), tool
        assert "undo" not in tool and "--yes" not in tool and "--exact" not in tool
    body = (SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
    assert "asks the user for permission" in body


def test_save_skill_passes_the_message_after_double_dash():
    body = (SKILLS_DIR / "save" / "SKILL.md").read_text(encoding="utf-8")
    assert "config-history save -- '<message>'" in body


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
