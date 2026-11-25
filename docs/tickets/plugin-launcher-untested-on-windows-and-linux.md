# The plugin launcher and wrapper have only ever run on macOS

Status: OPEN · Priority: MEDIUM · Type: verification gap · Cost: none

> Update 2026-11-25, first CI run on Linux and Windows (pull request #8, run
> 45678849145, all 15 jobs green). Linux is no longer unrun: the suite passed
> on `ubuntu-latest` 3.10 to 3.13 and `ubuntu-24.04` 3.9 with
> `625 passed, 2 skipped`, both skips in `tests/test_plugin_shell.py`, the
> rest of that file's launcher and wrapper tests running through the
> runner's `sh`. Which two tests skip there and why was not looked at.
> Windows is unchanged in substance: `593 passed, 22 skipped`, and 16 of the
> 22 skips are `tests/test_plugin_shell.py`, so the launcher and the wrapper
> still never run on Windows, not through Git Bash and not in a real install.
> Six of those skips were added in this pass with a stated reason (no
> `/bin/sh` and no shell-script fake Python; no POSIX executable bit; no POSIX
> permission bits for the two owner-only pointer file tests in
> `tests/test_plugin_bootstrap.py`). The Python side of the bootstrap now runs
> on Windows in CI and uses `Scripts\python.exe`. A real install on either
> system has still not been tried.

> Related: `plugin-not-tried-in-an-interactive-session.md` covers the
> interactive terminal on macOS. This one covers other operating systems.

## Symptom

`scripts/config-history-hook.sh` and `bin/config-history` are POSIX `sh`
scripts. Every run so far was on macOS (Darwin 27.2.0), with `sh` being bash.
Linux was never run. Windows was reviewed by reading only.

## Evidence

- Reviewer report, 2026-11-25: "Paths with spaces and quotes worked under dash
  and sh", run on this Mac. "Could not check: Windows at runtime. The `uv` path
  (not installed)."
- One Windows bug was found by reading and fixed without a Windows run: the
  pointer file was written in text mode (CRLF) and the wrapper kept the CR
  (`scripts/config_history_state.py`, `bin/config-history`). Tests
  `test_pointer_file_has_unix_line_ending_under_windows_text_mode` and
  `test_wrapper_reads_a_pointer_file_with_windows_line_ending` simulate it.
- On a case-sensitive disk the path-matching rule (decision row 8) was tested
  with a forced probe answer, not on a real case-sensitive filesystem.
- CI (`.github/workflows/ci.yml`) runs the Python suite on Linux, macOS and
  Windows, but only on pushes to `main` and pull requests against `main`. The
  new matrix, including the macOS 3.9 x64 job, has therefore never run on this
  work; pushing the feature branch alone does not start it.

## Why it matters

The README says the plugin was tested on macOS only. A Windows user would run
the hook through Git Bash or PowerShell; if the launcher fails there, the user
gets no history and possibly an error on every session start.

## Scope to decide

- Run the hook, the wrapper and one install on a Linux machine or container and
  on Windows with Git Bash, and record the results.
- OR state Windows as unsupported in the plugin description until someone
  tests it.
- Open a pull request against `main` to get a first CI run of the full matrix
  either way.

No code change made by this ticket. It is an observation on the record.
