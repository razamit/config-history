# The plugin's install pins runtime packages but not the build tools

Status: OPEN · Priority: LOW · Type: supply chain, reproducibility · Cost: none

## Symptom

`scripts/plugin-constraints.txt` pins the runtime packages the plugin installs
into its private environment. The build backend that pip fetches to build the
package from the plugin folder is not pinned, and nothing is hash-checked.

## Evidence

```
$ grep -n "setuptools\|wheel" pyproject.toml scripts/plugin-constraints.txt
pyproject.toml:2:requires = ["setuptools>=68", "wheel"]
pyproject.toml:3:build-backend = "setuptools.build_meta"
```

No match in `scripts/plugin-constraints.txt`. Fix-pass report, 2026-11-25:
"Build tools (`setuptools`, `wheel`) are not pinned."

The install log from a real run shows the runtime pins taking effect
(`click-8.5.1 cryptography-50.0.2 ... rich-15.0.0`).

## Why it matters

The install runs on a user's machine at first session start, without the user
choosing versions. Pinning the runtime packages covers most of the surface; an
unpinned build backend leaves a smaller one. Exact pins also are not hashes, so
they give reproducibility, not integrity.

## Scope to decide

- Pin `setuptools` and `wheel` to exact versions in `[build-system].requires`.
- OR ship a prebuilt wheel inside the plugin so no build step runs on the
  user's machine.
- OR add `--require-hashes` with a hash-locked file, at the cost of maintaining
  hashes per platform and Python version.
- OR accept it as is; the README already says the first run downloads from
  PyPI.

No code change made by this ticket. It is an observation on the record.
