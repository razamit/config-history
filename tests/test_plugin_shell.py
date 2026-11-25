"""Runs the plugin's sh scripts for real against fake Python executables.

The launcher (scripts/config-history-hook.sh) and the wrapper
(bin/config-history) are copied into a temp plugin root whose path contains a
space. PATH holds only a temp folder of fakes, so no real Python or tool runs.
Each test runs under /bin/sh and, when present, /bin/dash to catch bashisms.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "scripts" / "config-history-hook.sh"
WRAPPER = REPO_ROOT / "bin" / "config-history"
HOOKS_FILE = REPO_ROOT / "hooks" / "hooks.json"

SHELLS = [shell for shell in ("/bin/sh", "/bin/dash") if os.path.exists(shell)]

# Answers the launcher's version check, then echoes its arguments one per line.
FAKE_PYTHON = """#!/bin/sh
if [ "$1" = "-c" ]; then exit {version_check_exit}; fi
printf 'PROGRAM=%s\\n' "$CLAUDE_CFG_PROGRAM_NAME"
for argument in "$@"; do printf 'ARG=%s\\n' "$argument"; done
"""


def write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)
    return path


def fake_python(path: Path, supported: bool = True) -> Path:
    return write_executable(path, FAKE_PYTHON.format(version_check_exit=0 if supported else 1))


@pytest.fixture
def sandbox(tmp_path):
    plugin_root = tmp_path / "plugin root"
    shutil.copy(LAUNCHER, write_executable(plugin_root / "scripts" / LAUNCHER.name, ""))
    shutil.copy(WRAPPER, write_executable(plugin_root / "bin" / WRAPPER.name, ""))
    fake_bin = tmp_path / "fake bin"
    fake_bin.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": str(fake_bin), "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(plugin_root),
           "CLAUDE_PLUGIN_DATA": str(tmp_path / "data")}
    return {"root": plugin_root, "bin": fake_bin, "home": home, "env": env}


# Prints the day the test chooses, so "once per day" is deterministic.
FAKE_DATE = """#!/bin/sh
printf '%s\\n' "$FAKE_DAY"
"""
FAILING_XCODE_SELECT = "#!/bin/sh\nexit 2\n"


def run_script(shell, script: Path, args, env, cwd=None):
    return subprocess.run([shell, str(script), *args], env=env, capture_output=True, text=True,
                          timeout=30, cwd=cwd)


def add_date_and_mkdir(fake_bin: Path) -> None:
    write_executable(fake_bin / "date", FAKE_DATE)
    os.symlink(shutil.which("mkdir"), str(fake_bin / "mkdir"))


def argument_lines(output: str):
    return [line[len("ARG="):] for line in output.splitlines() if line.startswith("ARG=")]


@pytest.mark.parametrize("shell", SHELLS)
def test_launcher_runs_bootstrap_with_first_supported_python(shell, sandbox):
    fake_python(sandbox["bin"] / "python3.13", supported=False)
    fake_python(sandbox["bin"] / "python3.12")
    fake_python(sandbox["bin"] / "python3")
    script = sandbox["root"] / "scripts" / LAUNCHER.name
    result = run_script(shell, script, ["start"], sandbox["env"])
    assert result.returncode == 0, result.stderr
    bootstrap_path = str(sandbox["root"] / "scripts" / "config_history_bootstrap.py")
    assert argument_lines(result.stdout) == ["-B", "-E", "-s", bootstrap_path, "start"]


@pytest.mark.parametrize("shell", SHELLS)
def test_launcher_falls_back_to_plain_python(shell, sandbox):
    fake_python(sandbox["bin"] / "python3", supported=False)
    fake_python(sandbox["bin"] / "python")
    script = sandbox["root"] / "scripts" / LAUNCHER.name
    result = run_script(shell, script, ["end"], sandbox["env"])
    assert result.returncode == 0
    assert argument_lines(result.stdout)[-1] == "end"


def needs_python_lines(result):
    assert result.returncode == 0, result.stderr
    return [json.loads(line)["systemMessage"] for line in result.stdout.splitlines()]


@pytest.mark.parametrize("shell", SHELLS)
def test_launcher_without_python_reports_once_per_day(shell, sandbox):
    add_date_and_mkdir(sandbox["bin"])
    script = sandbox["root"] / "scripts" / LAUNCHER.name
    env = dict(sandbox["env"], FAKE_DAY="2026-11-25")
    (first,) = needs_python_lines(run_script(shell, script, ["start"], env))
    assert "Python 3.9 or later" in first
    assert needs_python_lines(run_script(shell, script, ["start"], env)) == []
    assert needs_python_lines(run_script(shell, script, ["end"], env)) == []
    stamp = Path(env["CLAUDE_PLUGIN_DATA"]) / "python-missing-notice"
    assert stamp.read_text() == "2026-11-25\n"
    next_day = dict(env, FAKE_DAY="2026-11-26")
    assert len(needs_python_lines(run_script(shell, script, ["start"], next_day))) == 1


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.skipif(sys.platform != "darwin", reason="the /usr/bin/python3 stub is macOS only")
def test_launcher_skips_macos_stub_without_command_line_tools(shell, sandbox):
    """/usr/bin/ on PATH makes some shells report /usr/bin//python3; still a stub."""
    others = [name for name in ("python", "python3.9", "python3.12", "python3.13")
              if os.path.exists("/usr/bin/" + name)]
    if others or not os.path.exists("/usr/bin/python3"):
        pytest.skip("/usr/bin has other Pythons or no python3")
    add_date_and_mkdir(sandbox["bin"])
    write_executable(sandbox["bin"] / "xcode-select", FAILING_XCODE_SELECT)
    env = dict(sandbox["env"], FAKE_DAY="2026-11-25", PATH=str(sandbox["bin"]) + ":/usr/bin/")
    result = run_script(shell, sandbox["root"] / "scripts" / LAUNCHER.name, ["start"], env)
    (message,) = needs_python_lines(result)
    assert "Python 3.9 or later" in message


@pytest.mark.parametrize("event", ["SessionStart", "SessionEnd"])
@pytest.mark.skipif(sys.platform == "win32",
                    reason="needs /bin/sh and a shell-script fake python, which Windows does not have")
def test_hook_command_from_hooks_json_runs_through_sh(event, sandbox):
    """Runs the hooks.json command string the way Claude Code does, with sh -c."""
    os.symlink("/bin/sh", str(sandbox["bin"] / "sh"))
    fake_python(sandbox["bin"] / "python3")
    command = json.loads(HOOKS_FILE.read_text())["hooks"][event][0]["hooks"][0]["command"]
    result = subprocess.run(["/bin/sh", "-c", command], env=sandbox["env"], capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected_event = "start" if event == "SessionStart" else "end"
    assert argument_lines(result.stdout)[-2:] == [
        str(sandbox["root"] / "scripts" / "config_history_bootstrap.py"), expected_event]


@pytest.mark.parametrize("shell", SHELLS)
def test_wrapper_execs_venv_python_with_program_name(shell, sandbox, tmp_path):
    venv_python = fake_python(tmp_path / "data dir" / "venv" / "bin" / "python")
    tool_home = tmp_path / "tool home"
    tool_home.mkdir()
    (tool_home / "plugin-python").write_text(str(venv_python) + "\n")
    env = dict(sandbox["env"], CLAUDE_CFG_HOME=str(tool_home))
    wrapper = sandbox["root"] / "bin" / WRAPPER.name
    result = run_script(shell, wrapper, ["save", "two words; and 'quotes'"], env)
    assert result.returncode == 0, result.stderr
    assert "PROGRAM=config-history" in result.stdout.splitlines()
    assert argument_lines(result.stdout) == ["-I", "-m", "claude_cfg", "save",
                                             "two words; and 'quotes'"]


@pytest.mark.parametrize("shell", SHELLS)
def test_wrapper_uses_default_tool_home(shell, sandbox, tmp_path):
    venv_python = fake_python(tmp_path / "venv" / "bin" / "python")
    pointer = sandbox["home"] / ".claude-cfg" / "plugin-python"
    pointer.parent.mkdir()
    pointer.write_text(str(venv_python))  # no trailing newline
    result = run_script(shell, sandbox["root"] / "bin" / WRAPPER.name, ["list"], sandbox["env"])
    assert result.returncode == 0, result.stderr
    assert argument_lines(result.stdout)[-1] == "list"


@pytest.mark.parametrize("shell", SHELLS)
def test_wrapper_reads_a_pointer_file_with_windows_line_ending(shell, sandbox, tmp_path):
    venv_python = fake_python(tmp_path / "venv" / "bin" / "python")
    pointer = sandbox["home"] / ".claude-cfg" / "plugin-python"
    pointer.parent.mkdir()
    pointer.write_bytes(str(venv_python).encode() + b"\r\n")
    result = run_script(shell, sandbox["root"] / "bin" / WRAPPER.name, ["list"], sandbox["env"])
    assert result.returncode == 0, result.stderr
    assert argument_lines(result.stdout)[-1] == "list"


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("configured", ["project-home", "~/x", "./project-home"])
def test_wrapper_ignores_a_relative_tool_home(shell, sandbox, tmp_path, configured):
    """A project folder must not choose which Python the wrapper runs."""
    project = tmp_path / "project"
    planted = fake_python(project / "planted" / "python")
    for folder in (project / "project-home", sandbox["home"] / "x"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plugin-python").write_text(str(planted) + "\n")
    env = dict(sandbox["env"], CLAUDE_CFG_HOME=configured)
    result = run_script(shell, sandbox["root"] / "bin" / WRAPPER.name, ["list"], env, cwd=project)
    assert result.returncode == 1
    assert "still setting up" in result.stderr and "ARG=" not in result.stdout


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("pointer_content", [None, "/nowhere/venv/bin/python\n"])
def test_wrapper_without_environment_explains_and_exits_1(shell, sandbox, pointer_content):
    if pointer_content is not None:
        pointer = sandbox["home"] / ".claude-cfg" / "plugin-python"
        pointer.parent.mkdir()
        pointer.write_text(pointer_content)
    result = run_script(shell, sandbox["root"] / "bin" / WRAPPER.name, ["status"], sandbox["env"])
    assert result.returncode == 1
    output = (result.stdout + result.stderr).strip().splitlines()
    assert len(output) == 1
    assert "still setting up or was not set up" in output[0]
    assert "Start a new Claude Code session" in output[0]


@pytest.mark.parametrize("path", [WRAPPER, LAUNCHER])
@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows file systems have no POSIX executable bit")
def test_scripts_are_executable_on_disk(path):
    assert path.stat().st_mode & stat.S_IXUSR


def test_wrapper_is_executable_in_git_index_when_tracked():
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    listing = subprocess.run(["git", "ls-files", "-s", "--", "bin/config-history"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
    if listing.returncode != 0 or not listing.stdout.strip():
        pytest.skip("bin/config-history is not tracked by git yet")
    assert listing.stdout.split()[0] == "100755"
