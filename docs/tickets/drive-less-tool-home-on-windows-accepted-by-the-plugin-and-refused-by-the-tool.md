# On Windows, `CLAUDE_CFG_HOME=/srv/x` is accepted by the plugin scripts and refused by the tool

Status: OPEN · Priority: LOW · Type: inconsistency, Windows only · Cost: none

> Found by reading during the CI fix pass on pull request #8, 2026-11-25.
> Not reproduced: nothing here was run on a Windows machine. Same family as
> the relative `CLAUDE_CFG_HOME` fix listed under Fixed in `CHANGELOG.md`.

## Symptom

A rooted path with no drive letter, such as `/srv/x`, counts as absolute for
the plugin's bootstrap and for the `bin/config-history` wrapper, and as not
absolute for the Python package on Windows. The two halves would then use
different folders: the plugin writes its pointer file under `/srv/x`, and the
tool falls back to `~/.claude-cfg` for the history and the config.

## Evidence

```
scripts/config_history_state.py:86   return posixpath.isabs(path) or (ntpath.isabs(path) and bool(ntpath.splitdrive(path)[0]))
claude_cfg/paths.py:82                return candidate if candidate.is_absolute() else None
```

`pathlib.Path("/srv/x").is_absolute()` is `False` on Windows, on every Python
version. `posixpath.isabs("/srv/x")` is `True` everywhere. The first line was
changed in commit `2309a20` so its answer no longer depends on the Python
version (before that it was accepted on Python 3.12 and refused on 3.13); the
second was left alone.

## Why it matters

Little. It needs a Windows user who sets `CLAUDE_CFG_HOME` by hand to a path
without a drive letter. In Git Bash such a path may also be rewritten to a
location under the Git install before any of this code sees it, which was not
checked.

## Scope to decide

- Make the package apply the same three-form rule as the scripts.
- OR make the scripts refuse a drive-less path on Windows, as the package does.
- OR leave it and document that `CLAUDE_CFG_HOME` on Windows needs a drive
  letter.

No code change made by this ticket. It is an observation on the record.
