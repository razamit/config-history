import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Portable tokens. Stored snapshots use these instead of machine-specific
# absolute paths so a snapshot taken on one OS restores cleanly on any other.
HOME_TOKEN = "${HOME}"
CLAUDE_TOKEN = "${CLAUDE_HOME}"
# The python launcher a command spells differs by OS (``python`` on Windows,
# ``python3`` on macOS/most Linux). Snapshots store this neutral token and the
# restore resolves it to whatever actually exists on the target machine.
PYTHON_TOKEN = "${PYTHON}"

_PYTHON_CANDIDATES = ("python3", "python")


def resolve_python() -> str:
    """The python launcher to bake into restored commands on this machine.

    Prefers ``python3`` (POSIX and modern installs) and falls back to ``python``
    (typical on Windows). Defaults to ``python3`` if neither is on PATH, so a
    restored command is at least well-formed and fixable.
    """
    for candidate in _PYTHON_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return "python3"


def _home() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("USERPROFILE") or Path.home())
    return Path.home()


CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
CLAUDE_JSON_NAME = ".claude.json"


def home_dir() -> Path:
    """This user's home folder."""
    return _home()


def _configured_claude_dir() -> Optional[Path]:
    """The folder ``CLAUDE_CONFIG_DIR`` names, when it is an absolute path."""
    raw = os.environ.get(CLAUDE_CONFIG_DIR_ENV, "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else None


def claude_dir() -> Path:
    """Where Claude Code keeps its config: ``CLAUDE_CONFIG_DIR`` or ``~/.claude``."""
    return _configured_claude_dir() or _home() / ".claude"


def claude_json_file() -> Path:
    """Claude Code's ``.claude.json``.

    It moves inside ``CLAUDE_CONFIG_DIR`` when that is set, and otherwise sits
    in the home folder next to ``.claude``.
    """
    configured = _configured_claude_dir()
    return (configured or _home()) / CLAUDE_JSON_NAME


CLAUDE_CFG_HOME_ENV = "CLAUDE_CFG_HOME"


def _configured_tool_dir() -> Optional[Path]:
    """The folder ``CLAUDE_CFG_HOME`` names, when it is an absolute path."""
    raw = os.environ.get(CLAUDE_CFG_HOME_ENV, "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else None


def config_dir() -> Path:
    """This tool's own folder: ``CLAUDE_CFG_HOME`` or ``~/.claude-cfg``.

    The config, the sync state, pull backups and the default local history
    all live here.
    """
    return _configured_tool_dir() or _home() / ".claude-cfg"


def config_file() -> Path:
    return config_dir() / "config.json"


def backups_dir() -> Path:
    return config_dir() / "backups"


def state_file() -> Path:
    return config_dir() / "state.json"


def history_dir() -> Path:
    """Where the default local history keeps its versions."""
    return config_dir() / "history"


def autosave_lock_file() -> Path:
    """Held while an automatic save runs, so two sessions never save at once."""
    return config_dir() / "autosave.lock"


@dataclass
class Target:
    """The machine a snapshot is being captured from or restored to."""

    platform: str  # win32 | darwin | linux
    home: Path
    claude_home: Path
    sep: str  # native path separator for shell-bound fields
    is_wsl: bool
    python: str  # python launcher available on this machine


# Older manifests wrote ``platform.system().lower()``; map those names onto
# the ones used everywhere now.
_LEGACY_PLATFORM_NAMES = {"windows": "win32"}


def platform_name() -> str:
    """This machine's platform as manifests and targets name it: win32, darwin or linux."""
    system = platform.system()
    if system == "Windows":
        return "win32"
    if system == "Darwin":
        return "darwin"
    return "linux"


def normalize_platform_name(name: str) -> str:
    """A platform name from any manifest, in the current naming."""
    lowered = str(name).lower()
    return _LEGACY_PLATFORM_NAMES.get(lowered, lowered)


def detect_target() -> Target:
    plat = platform_name()
    sep = "\\" if plat == "win32" else "/"
    is_wsl = "microsoft" in platform.uname().release.lower()
    home = _home()
    return Target(
        platform=plat,
        home=home,
        claude_home=claude_dir(),
        sep=sep,
        is_wsl=is_wsl,
        python=resolve_python(),
    )


# A path token is followed by its tail up to the next whitespace or quote.
_TAIL = r'([^\s"\'`]*)'


def _default_claude_home(home: Path) -> Path:
    return home / ".claude"


def collapse_paths(value: str, home: Path, claude_home: Optional[Path] = None) -> str:
    """Replace machine-specific home and Claude folder paths with portable tokens.

    ``claude_home`` defaults to ``home/.claude``; pass it when
    ``CLAUDE_CONFIG_DIR`` puts the Claude folder somewhere else. Matches
    absolute paths (either separator style) and normalizes the captured tail
    to ``/`` so the stored form is OS-neutral. The ``~/.claude`` shortcut is
    only the Claude folder when that folder really is ``home/.claude``.
    """
    claude_home = claude_home if claude_home is not None else _default_claude_home(home)
    flags = re.IGNORECASE if os.name == "nt" else 0
    bases = [
        (str(claude_home), CLAUDE_TOKEN),
        (claude_home.as_posix(), CLAUDE_TOKEN),
        (str(home), HOME_TOKEN),
        (home.as_posix(), HOME_TOKEN),
    ]
    if claude_home == _default_claude_home(home):
        bases.append(("~/.claude", CLAUDE_TOKEN))
    # Most specific first, so a Claude folder inside home wins over home.
    bases.sort(key=lambda base_and_token: len(base_and_token[0]), reverse=True)
    out = value
    for base, token in bases:
        pattern = re.compile(re.escape(base) + _TAIL, flags)
        out = pattern.sub(lambda m: token + m.group(1).replace("\\", "/"), out)
    return out


def expand_paths(
    value: str, home: Path, sep: str, claude_home: Optional[Path] = None
) -> str:
    """Reverse of :func:`collapse_paths` against a target machine.

    Tokens become native absolute paths; tails are converted to ``sep`` so the
    result is valid on the restoring OS (backslashes on Windows, slashes else).
    """
    claude_home = claude_home if claude_home is not None else _default_claude_home(home)
    out = value
    for token, base in ((CLAUDE_TOKEN, str(claude_home)), (HOME_TOKEN, str(home))):
        pattern = re.compile(re.escape(token) + _TAIL)
        out = pattern.sub(
            lambda m: base + (m.group(1) if sep == "/" else m.group(1).replace("/", sep)),
            out,
        )
    return out


# A bare python launcher at the very start of a command: python, python3,
# python2, python3.11, optionally with a Windows .exe suffix. It must be
# followed by whitespace (i.e. it has arguments) so the lone word "python" in
# prose is never touched. Path-qualified interpreters (``/usr/bin/python3``, a
# venv path) are deliberately left alone. Those are explicit, machine-specific
# choices we must not second-guess.
_PYTHON_LAUNCHER_RE = re.compile(
    r'^(\s*)python(?:[23](?:\.\d{1,2})?)?(?:\.exe)?(?=\s)',
    re.IGNORECASE,
)
# Only normalize when the command actually runs a script: a .py file, a path
# separator, or one of our path tokens appears. Keeps us off plain prose.
_SCRIPT_HINT_RE = re.compile(r'\.pyw?\b|[/\\]|\$\{(?:CLAUDE_HOME|HOME)\}')


def collapse_interpreter(value: str) -> str:
    """Capture-side: a leading bare ``python`` launcher -> ``${PYTHON}`` token.

    Run after :func:`collapse_paths`, so script paths are already tokenized and
    available as a hint that this string is a command rather than prose.
    """
    if not _SCRIPT_HINT_RE.search(value):
        return value
    return _PYTHON_LAUNCHER_RE.sub(lambda m: m.group(1) + PYTHON_TOKEN, value)


def expand_interpreter(value: str, python_cmd: str) -> str:
    """Restore-side: ``${PYTHON}`` token -> the launcher this machine has."""
    return value.replace(PYTHON_TOKEN, python_cmd)
