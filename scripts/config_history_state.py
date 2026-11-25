"""File-based state for the config-history plugin bootstrap.

Stdlib only and compatible with Python 3.9. Holds the paths the bootstrap uses,
the install marker, the private environments and the pointer file that the
bin/config-history wrapper reads. The install lock and the failure status are
in config_history_install_records.py.

Each install builds a new environment in its own folder beside the current
one (``venv-<time>`` in the plugin data folder). The marker names the
environment in use, so a failed build never touches the working one.
"""

from __future__ import annotations

import json
import ntpath
import os
import re
import shutil
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional

PROGRAM_NAME = "config-history"
# The folder installs before this layout used, named by a marker without an
# "environment" field.
LEGACY_ENVIRONMENT = "venv"
_ENVIRONMENT_NAME = re.compile(r"^venv(-[0-9]+)?$")

Clock = Callable[[], float]


@dataclass(frozen=True)
class BootstrapPaths:
    """Every path the bootstrap reads or writes."""

    plugin_root: str
    data_dir: str
    tool_home: str
    is_windows: bool = False

    def environment_dir(self, name: str) -> str:
        return os.path.join(self.data_dir, name)

    def environment_python(self, name: str) -> str:
        if self.is_windows:
            return os.path.join(self.environment_dir(name), "Scripts", "python.exe")
        return os.path.join(self.environment_dir(name), "bin", "python")

    @property
    def marker_file(self) -> str:
        return os.path.join(self.data_dir, "install-marker.json")

    @property
    def lock_file(self) -> str:
        return os.path.join(self.data_dir, "install.lock")

    @property
    def status_file(self) -> str:
        return os.path.join(self.data_dir, "install-status.json")

    @property
    def log_file(self) -> str:
        return os.path.join(self.data_dir, "install.log")

    @property
    def staging_dir(self) -> str:
        return os.path.join(self.data_dir, "build-source")

    @property
    def pointer_file(self) -> str:
        return os.path.join(self.tool_home, "plugin-python")

    @property
    def manifest_file(self) -> str:
        return os.path.join(self.plugin_root, ".claude-plugin", "plugin.json")


def is_absolute_path(path: str) -> bool:
    """True for a POSIX absolute path or a Windows drive or UNC path."""
    return os.path.isabs(path) or (ntpath.isabs(path) and bool(ntpath.splitdrive(path)[0]))


def resolve_tool_home(env: Mapping[str, str]) -> str:
    """Return the tool's own folder: CLAUDE_CFG_HOME when absolute, else ~/.claude-cfg.

    A relative or ``~`` value is ignored, the same as the package does
    (claude_cfg/paths.py), so the pointer file is never read from a folder
    that depends on the current directory.
    """
    home = env.get("HOME") or env.get("USERPROFILE") or os.path.expanduser("~")
    configured = env.get("CLAUDE_CFG_HOME", "").strip()
    if configured and is_absolute_path(configured):
        return configured
    return os.path.join(home, ".claude-cfg")


def resolve_paths(
    env: Mapping[str, str], fallback_plugin_root: str, is_windows: bool = False
) -> Optional[BootstrapPaths]:
    """Build the paths from the hook environment, or None without a data dir."""
    data_dir = env.get("CLAUDE_PLUGIN_DATA", "").strip()
    if not data_dir:
        return None
    plugin_root = env.get("CLAUDE_PLUGIN_ROOT", "").strip() or fallback_plugin_root
    return BootstrapPaths(
        plugin_root=os.path.abspath(plugin_root),
        data_dir=os.path.abspath(data_dir),
        tool_home=resolve_tool_home(env),
        is_windows=is_windows,
    )


def read_json_file(path: str) -> Optional[dict]:
    """Return the JSON object in path, or None when missing or unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def write_private_text(path: str, text: str) -> None:
    """Write text atomically to a file readable only by its owner."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, mode=0o700, exist_ok=True)
    temporary_path = path + ".tmp"
    descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # newline="\n": no CRLF on Windows, where the sh wrapper reads the pointer file.
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, path)


def write_json_file(path: str, content: dict) -> None:
    write_private_text(path, json.dumps(content, indent=2, sort_keys=True) + "\n")


def remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def read_plugin_version(paths: BootstrapPaths) -> str:
    """Return the version in the plugin manifest, or an empty string."""
    manifest = read_json_file(paths.manifest_file) or {}
    version = manifest.get("version")
    return version if isinstance(version, str) else ""


def install_target(paths: BootstrapPaths) -> dict:
    """The plugin version and root an install is for."""
    return {"version": read_plugin_version(paths), "plugin_root": paths.plugin_root}


def read_marker(paths: BootstrapPaths) -> Optional[dict]:
    return read_json_file(paths.marker_file)


def write_marker(paths: BootstrapPaths, environment: str) -> None:
    write_json_file(paths.marker_file, dict(install_target(paths), environment=environment))


def installed_environment(paths: BootstrapPaths) -> Optional[str]:
    """The environment the marker names, or None without a usable marker."""
    marker = read_marker(paths)
    if marker is None:
        return None
    name = marker.get("environment", LEGACY_ENVIRONMENT)
    return name if isinstance(name, str) and _ENVIRONMENT_NAME.match(name) else None


def installed_python(paths: BootstrapPaths) -> Optional[str]:
    """The Python of the environment in use, whatever version it was built for."""
    name = installed_environment(paths)
    if name is None:
        return None
    python = paths.environment_python(name)
    return python if os.path.isfile(python) else None


def marker_matches(paths: BootstrapPaths) -> bool:
    """True when the environment in use matches this plugin version and root."""
    if installed_python(paths) is None:
        return False
    marker = read_marker(paths) or {}
    target = install_target(paths)
    return all(marker.get(key) == value for key, value in target.items())


def new_environment_name(now: float) -> str:
    return "venv-{}".format(int(now))


def remove_environments_except(paths: BootstrapPaths, keep: Iterable[Optional[str]]) -> None:
    """Delete environment folders other than ``keep`` (current and previous)."""
    kept = {name for name in keep if name}
    try:
        names = os.listdir(paths.data_dir)
    except OSError:
        return
    for name in names:
        if _ENVIRONMENT_NAME.match(name) and name not in kept:
            shutil.rmtree(paths.environment_dir(name), ignore_errors=True)


def write_pointer_file(paths: BootstrapPaths, python_path: str) -> None:
    """Record the environment's Python for bin/config-history, owner-only."""
    wanted = python_path + "\n"
    try:
        with open(paths.pointer_file, "r", encoding="utf-8", newline="") as handle:
            if handle.read() == wanted:
                return
    except OSError:
        pass
    write_private_text(paths.pointer_file, wanted)
