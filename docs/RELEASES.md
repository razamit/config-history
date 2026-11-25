# Releases

Every file that carries the version, listed once, and every release cut.
Detected at init or on the first release action; re-detected only by
`/devlog:releases status` or when a listed path no longer exists. The
changelog section for each release is written from the progress entries
stamped with that version.

## Carriers
- Canonical: `pyproject.toml` `[project].version`
- Mirrors: `claude_cfg/__init__.py` `__version__`; `.claude-plugin/plugin.json` `version`
- Derived, do not edit: none. The README's PyPI badge reads the published version.
- Build number: none
- Tag: `vX.Y.Z`, annotated, latest `v0.2.0`
- Changelog style: `## [X.Y.Z] - YYYY-MM-DD`
- Bump policy: decision row 2

Notes for whoever cuts a release:
- Pushing a `v*.*.*` tag runs `.github/workflows/release.yml`, which builds,
  publishes to PyPI and creates a GitHub release. A tag push is the release.
- `tests/test_plugin_manifest.py` fails when the plugin version and the package
  version differ, so the three carriers move together.
- `scripts/plugin-constraints.txt` pins the versions the plugin installs and is
  reviewed with each release.
- The carriers already read 0.3.0 and nothing has been cut: `CHANGELOG.md` holds
  that work under `## [Unreleased]`.

## Index, newest first

| Version | Date | Build | Tag → commit | Shipped | Post |
|---|---|---|---|---|---|
| 0.2.0 | 2026-06-09 | none | v0.2.0 → 18e1acf | not checked | |
| 0.1.0 | 2026-05-07 | none | v0.1.0 → e382a17 | not checked | |
