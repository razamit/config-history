# CI tests against the newest Typer on Python 3.10 and later, while the plugin installs a pinned older one

Status: OPEN · Priority: LOW · Type: test coverage gap · Cost: none

> Surfaced by the CI fix pass on pull request #8, 2026-11-25. Related to
> `plugin-install-build-tools-not-pinned.md`, which is about the build tools
> of the plugin's environment; this one is about which dependency versions
> the test suite sees.

## Symptom

The plugin installs the versions in `scripts/plugin-constraints.txt`. CI runs
`pip install -e ".[dev]"`, which takes the newest versions `pyproject.toml`
allows. On Python 3.10 to 3.13 that is a Typer the plugin never installs, and
the two already differ in output.

## Evidence

```
scripts/plugin-constraints.txt:22:typer==0.23.2
pyproject.toml:30:    "typer>=0.12",
```

Run 45676976964 (pull request #8): every 3.10+ job failed
`tests/test_session_hook.py::test_save_and_restore_are_aliases`, because Typer
0.29.x prints the `save` argument as `[message]` where 0.23.2 prints
`[MESSAGE]`. The 3.9 jobs passed, since the newest Typer for 3.9 is 0.23.2.
The test now accepts either case (`tests/test_session_hook.py:194`).

The suite also depends on a Typer internal: `tests/conftest.py:41` sets
`typer.rich_utils.FORCE_TERMINAL` to `False` so help text is plain under
GitHub Actions. If Typer renames it, every test errors at setup, which is
loud, not silent.

## Why it matters

The plugin is what most users will run, and its exact dependency set is tested
only by accident, on the 3.9 jobs. A difference that matters more than letter
case would reach plugin users untested, or would fail CI for a version nobody
installs through the plugin.

## Scope to decide

- Add one CI job that installs with `-c scripts/plugin-constraints.txt`, so
  the pinned set is tested on purpose.
- OR raise the pins in the constraints file with each release and accept the
  gap in between (the release notes in `docs/RELEASES.md` already say the
  file is reviewed per release).
- OR leave it: the 3.9 jobs happen to cover the pinned Typer today.

No code change made by this ticket. It is an observation on the record.
