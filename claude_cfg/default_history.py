"""The local history that works with no setup.

Until the user runs ``init``, every command uses a config written on first
use: snapshots go to ``<config dir>/history`` on this machine, the default
tracked list, no encryption, no MCP server sync, and auto-save on. The
config carries ``automatic_default: true`` so ``init`` and ``status`` can
tell it apart from a setup the user chose.
"""

import os
from pathlib import Path
from typing import Optional

from claude_cfg import config as cfg_mod
from claude_cfg.config import (
    AUTOMATIC_DEFAULT_KEY,
    AUTOSAVE_KEY,
    DEFAULT_AUTOSAVE_KEEP,
    DEFAULT_TRACKED,
    ENCRYPTION_KEY,
    MCP_SERVERS_KEY,
    is_automatic_default,
)
from claude_cfg.paths import config_file, history_dir
from claude_cfg.private_file import PRIVATE_DIR_MODE, make_private_dirs
from claude_cfg.providers.local import LocalProvider
from claude_cfg.snapshot_keys import SNAPSHOT_PREFIX, parse_snapshot_key


def build_default_config() -> dict:
    """The automatic local-history config for this machine."""
    return {
        "storage": "local",
        "local": {"path": str(history_dir())},
        "tracked": list(DEFAULT_TRACKED),
        ENCRYPTION_KEY: {"enabled": False},
        MCP_SERVERS_KEY: {"enabled": False},
        AUTOSAVE_KEY: {"enabled": True, "keep": DEFAULT_AUTOSAVE_KEEP},
        AUTOMATIC_DEFAULT_KEY: True,
    }


def load_or_create_config() -> dict:
    """The saved config, or the automatic default written now when there is none.

    Two processes may both find no config and both write the default; they
    write the same text and each write replaces the file in one step.
    """
    try:
        return cfg_mod.load()
    except FileNotFoundError:
        pass
    default_config = build_default_config()
    try:
        cfg_mod.save(default_config)
    except OSError:
        if config_file().exists():
            return cfg_mod.load()
        raise
    make_private_dirs(history_dir())
    try:
        os.chmod(history_dir(), PRIVATE_DIR_MODE)  # also when it existed already
    except OSError:
        pass
    return default_config


def existing_local_history(cfg: Optional[dict]) -> Optional[tuple[Path, int]]:
    """The automatic history's folder and how many versions it holds, when
    ``cfg`` is the automatic default and the folder has at least one."""
    if not cfg or not is_automatic_default(cfg):
        return None
    local_section = cfg.get("local")
    if not isinstance(local_section, dict) or not local_section.get("path"):
        return None
    folder = Path(str(local_section["path"])).expanduser()
    if not folder.is_dir():
        return None
    keys = LocalProvider(cfg).list_keys(SNAPSHOT_PREFIX)
    count = sum(1 for key in keys if parse_snapshot_key(key) is not None)
    return (folder, count) if count else None
