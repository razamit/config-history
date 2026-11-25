import pytest

import claude_cfg.paths as paths_mod
from claude_cfg.command_runner import SubprocessCommandRunner
from claude_cfg.mcp_cli_preflight import CLAUDE_CODE_SESSION_ENV
from claude_cfg.passphrase import PASSPHRASE_ENV_VAR
from claude_cfg.program_name import PROGRAM_NAME_ENV


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    """Point every test at a throwaway home so nothing touches the real one.

    Also clears CLAUDECODE, which is set when the tests themselves run
    inside Claude Code, and the passphrase env var so a value set on this machine cannot
    change what a test sees, and clears CLAUDE_CONFIG_DIR so a value set on
    this machine can never point a test at a real Claude folder. The same
    goes for CLAUDE_CFG_HOME (the tool's own folder) and the program name.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(paths_mod, "_home", lambda: home)
    monkeypatch.delenv(PASSPHRASE_ENV_VAR, raising=False)
    monkeypatch.delenv(paths_mod.CLAUDE_CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv(paths_mod.CLAUDE_CFG_HOME_ENV, raising=False)
    monkeypatch.delenv(PROGRAM_NAME_ENV, raising=False)
    monkeypatch.delenv(CLAUDE_CODE_SESSION_ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CFG_DEBUG", raising=False)
    return home


class RealCommandRunAttempted(AssertionError):
    """A test reached the real command runner instead of an injected one."""


@pytest.fixture(autouse=True)
def no_real_commands(monkeypatch):
    """Make the default runner fail loudly, so no test can reach the real
    ``claude`` binary by accident. Tests that need a runner inject one."""

    def refuse(self, arguments, stdin_text=None):
        raise RealCommandRunAttempted(f"A test tried to run a real command: {arguments[0]!r}")

    monkeypatch.setattr(SubprocessCommandRunner, "run", refuse)
