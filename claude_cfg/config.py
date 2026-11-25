import json
from typing import Any

from claude_cfg.paths import config_file, config_dir
from claude_cfg.private_file import make_private_dirs, write_private_bytes
from claude_cfg.program_name import command_hint

DEFAULT_TRACKED = [
    "settings.json",
    "CLAUDE.md",
    "commands/",
    "skills/",
    "agents/",
    "plugins/",
    "keybindings.json",
    "themes/",
    "rules/",
    "output-styles/",
    "workflows/",
]

_MASKED_KEYS = {
    "access_key", "secret_key", "token", "password", "passphrase", "passphrase_verifier",
}

ENCRYPTION_KEY = "encryption"
VERIFIER_KEY = "passphrase_verifier"
_TRUE_STRINGS = {"true", "1", "yes", "on"}


def is_masked_key(key: str) -> bool:
    """True when values stored under ``key`` are secrets to hide on display."""
    return key in _MASKED_KEYS


def encryption_settings(cfg: dict) -> dict:
    """The ``encryption`` section of a config, or an empty dict."""
    section = cfg.get(ENCRYPTION_KEY)
    return section if isinstance(section, dict) else {}


def _is_truthy(value: Any) -> bool:
    """A real boolean, or one of the strings ``config set`` stores."""
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return bool(value)


def is_encryption_enabled(cfg: dict) -> bool:
    """Whether new pushes should be encrypted.

    Accepts the strings that ``config set encryption.enabled ...`` stores as
    well as real booleans. Configs without the section stay unencrypted.
    """
    return _is_truthy(encryption_settings(cfg).get("enabled", False))


MCP_SERVERS_KEY = "mcp_servers"


def is_mcp_sync_enabled(cfg: dict) -> bool:
    """Whether user-scope MCP servers are captured and restored.

    Off unless ``mcp_servers.enabled`` is set, so existing installs keep
    their behavior until they opt in.
    """
    section = cfg.get(MCP_SERVERS_KEY)
    return _is_truthy(section.get("enabled", False)) if isinstance(section, dict) else False


def set_mcp_sync_enabled(cfg: dict, enabled: bool) -> None:
    section = cfg.get(MCP_SERVERS_KEY)
    if not isinstance(section, dict):
        section = {}
        cfg[MCP_SERVERS_KEY] = section
    section["enabled"] = enabled


BACKUPS_KEY = "backups"
DEFAULT_BACKUPS_KEEP = 10


def backups_keep_count(cfg: dict) -> int:
    """How many pull backups to keep (``backups.keep``), at least 1.

    ``config set backups.keep 5`` stores the string "5", so strings are
    accepted. Anything unreadable falls back to the default of 10.
    """
    section = cfg.get(BACKUPS_KEY)
    raw = section.get("keep", DEFAULT_BACKUPS_KEEP) if isinstance(section, dict) else DEFAULT_BACKUPS_KEEP
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return DEFAULT_BACKUPS_KEEP


# Set on the config written automatically on first use (local history, no
# setup). ``init`` writes a config without it.
AUTOMATIC_DEFAULT_KEY = "automatic_default"
AUTOSAVE_KEY = "autosave"
DEFAULT_AUTOSAVE_KEEP = 50


def is_automatic_default(cfg: dict) -> bool:
    """Whether this is the automatic local-history config, not one from ``init``."""
    return cfg.get(AUTOMATIC_DEFAULT_KEY) is True and cfg.get("storage") == "local"


def autosave_settings(cfg: dict) -> dict:
    """The ``autosave`` section of a config, or an empty dict."""
    section = cfg.get(AUTOSAVE_KEY)
    return section if isinstance(section, dict) else {}


def is_autosave_enabled(cfg: dict) -> bool:
    """``autosave.enabled`` when set. Otherwise on for the automatic local
    history and off for a backend chosen in ``init``, since saving to a
    shared remote on every change is the user's decision."""
    section = autosave_settings(cfg)
    if "enabled" in section:
        return _is_truthy(section["enabled"])
    return is_automatic_default(cfg)


def _writable_autosave_section(cfg: dict) -> dict:
    section = cfg.get(AUTOSAVE_KEY)
    if not isinstance(section, dict):
        section = {}
        cfg[AUTOSAVE_KEY] = section
    return section


def set_autosave_enabled(cfg: dict, enabled: bool) -> None:
    _writable_autosave_section(cfg)["enabled"] = enabled


def set_autosave_keep(cfg: dict, keep: int) -> None:
    _writable_autosave_section(cfg)["keep"] = max(int(keep), 1)


def autosave_keep_count(cfg: dict) -> int:
    """How many automatic versions to keep (``autosave.keep``), at least 1."""
    raw = autosave_settings(cfg).get("keep", DEFAULT_AUTOSAVE_KEEP)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return DEFAULT_AUTOSAVE_KEEP


def load() -> dict:
    path = config_file()
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Run `{command_hint('init')}` first."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save(cfg: dict) -> None:
    """Write the config owner-only (0600) from the moment it is created."""
    make_private_dirs(config_dir())
    write_private_bytes(config_file(), json.dumps(cfg, indent=2).encode("utf-8"))


def store_passphrase_verifier(verifier: dict) -> bool:
    """Add a passphrase verifier to the saved config's encryption section.

    False when there is no readable config file to add it to; a verifier is
    a convenience, so failing to store one never stops a push or a pull.
    """
    try:
        cfg = load()
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict):
        return False
    section = cfg.get(ENCRYPTION_KEY)
    if not isinstance(section, dict):
        section = {}
        cfg[ENCRYPTION_KEY] = section
    section[VERIFIER_KEY] = verifier
    try:
        save(cfg)
    except OSError:
        return False
    return True


def masked(cfg: dict) -> dict:
    """Return config with credential values replaced by '***'."""
    result = {}
    for k, v in cfg.items():
        if isinstance(v, dict):
            result[k] = {
                sk: "***" if sk in _MASKED_KEYS else sv
                for sk, sv in v.items()
            }
        else:
            result[k] = v
    return result


def set_value(key_path: str, value: Any) -> None:
    """Set a dot-separated key path in config. E.g. 'r2.bucket'."""
    cfg = load()
    parts = key_path.split(".")
    target = cfg
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
    save(cfg)


def validate(cfg: dict) -> None:
    storage = cfg.get("storage")
    if not storage:
        raise ValueError("Config missing 'storage' key.")
    valid = {"s3", "r2", "local", "gist", "sftp"}
    if storage not in valid:
        raise ValueError(f"Unknown storage backend: {storage!r}. Valid: {valid}")
