"""Which paths under ~/.claude are never captured, compared or deleted.

Machine-bound state and the Claude login file are never captured, even if a
tracked folder happens to contain them. This keeps snapshots light, but it
does not make them safe to share: only .credentials.json is excluded, and
files such as settings.json can still hold API keys or tokens. Turn on
encryption (`claude-cfg config encrypt`) so the backend only sees ciphertext.

The same filter guards restore: a path it excludes is never listed as a local
extra and never deleted by an exact pull.

Every check runs on :func:`claude_cfg.path_identity.path_identity`, on every
platform, so ``.Credentials.json`` or ``Projects/`` are excluded the same as
their usual spelling. A case-insensitive disk would otherwise let such a name
overwrite or delete the real file.

The ``_external/`` folder is reserved for snapshot members that live outside
the Claude folder (see :mod:`claude_cfg.external_members`), so it is excluded
here and the file code never reads, writes or deletes anything under it.

``.claude.json`` and its backups are excluded because ``CLAUDE_CONFIG_DIR``
moves that file inside the tracked folder, and it holds machine state and
MCP definitions that are synced separately.

Under ``plugins/`` only an allowlist is captured: the list of installed
plugins and the list of known marketplaces. Everything else there is managed
by Claude Code: clones, caches, the plugin catalog, the blocklist, and each
plugin's private data folder at ``plugins/data/<id>/`` (a plugin's own
virtual environment lives there, so capturing it would also let a restore
overwrite files inside a running environment).
"""

from claude_cfg.external_members import EXTERNAL_FOLDER
from claude_cfg.path_identity import path_identity

EXCLUDED_NAMES = frozenset({".credentials.json", ".ds_store", "thumbs.db", ".claude.json"})
EXCLUDED_NAME_PREFIXES = (".claude.json.backup",)
EXCLUDED_TOP_FOLDERS = frozenset(
    {"projects", "todos", "statsig", "shell-snapshots", "ide", "logs", EXTERNAL_FOLDER.casefold()}
)
# Re-fetchable or derived directory trees, excluded wherever they appear. Plugin
# marketplaces are git clones and the cache is rebuilt from the JSON manifests,
# so only the small manifests need to travel, not thousands of cloned files.
# Claude Code downloads and manages skills/synced, plugins/synced and the
# skills trash itself, so those are not user config either.
EXCLUDED_SEGMENTS = frozenset({".git", "node_modules", "__pycache__"})
EXCLUDED_PREFIXES = (
    "skills/synced/",
    "skills/.trash/",
)
PLUGINS_FOLDER = "plugins"
# The only files under plugins/ that are captured, restored or deleted.
PLUGINS_ALLOWLIST = frozenset({"plugins/installed_plugins.json", "plugins/known_marketplaces.json"})


def _is_excluded_name(name: str) -> bool:
    return (
        name in EXCLUDED_NAMES
        or name.endswith(".log")
        or name.startswith(EXCLUDED_NAME_PREFIXES)
    )


def _is_outside_plugins_allowlist(parts: list) -> bool:
    """True for a path under plugins/ that is not one of the allowlisted files."""
    if parts[0] != PLUGINS_FOLDER or len(parts) == 1:
        return False
    return "/".join(parts) not in PLUGINS_ALLOWLIST


def is_excluded(relative_path: str) -> bool:
    """True when a path, relative to ~/.claude in posix form, is never synced."""
    identity = path_identity(relative_path)
    parts = identity.split("/")
    if _is_excluded_name(parts[-1]):
        return True
    if parts[0] in EXCLUDED_TOP_FOLDERS or _is_outside_plugins_allowlist(parts):
        return True
    if any(segment in EXCLUDED_SEGMENTS for segment in parts):
        return True
    return any(identity.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def is_excluded_folder(relative_folder: str) -> bool:
    """True when every file inside this folder is excluded, so a walk can skip it."""
    identity = path_identity(relative_folder)
    parts = identity.split("/")
    if parts[0] in EXCLUDED_TOP_FOLDERS:
        return True
    if parts[0] == PLUGINS_FOLDER and len(parts) > 1:
        return True  # the allowlisted files sit directly in plugins/
    if any(segment in EXCLUDED_SEGMENTS for segment in parts):
        return True
    with_slash = identity + "/"
    return any(with_slash.startswith(prefix) for prefix in EXCLUDED_PREFIXES)
