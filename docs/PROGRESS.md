# Implementation Progress

Newest entry first. One entry per completed unit of work: dated headline,
scope note, status marker (✅ DONE / 🟡 PARTIAL / ⛔ NOT STARTED), proof,
files touched, cross-refs to decisions and tickets. Never rewrite old entries.

---

**2026-11-25: Devlog system adopted (docs only, no code change). ✅ DONE.**
Scaffolded `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/tickets/` and
`docs/RELEASES.md`, and created `CLAUDE.md` with the devlog block. The existing
`CHANGELOG.md` was left as it is. The two entries below, decision rows 2 to 14
and the eight tickets were written in the same session that did the work, after
its three commits (`0fc294b`, `1bbbd01`, `461efef`), so those commits do not
contain their own log entries; this commit carries them. State at wrap: branch
`feat/hardening-and-coverage` is pushed after this commit and not merged, so
the plugin is not published. `origin/main` is 10 commits ahead of the branch
base (dependabot bumps to `.github/workflows/ci.yml` and `release.yml`) and
`git merge-tree` reports a clean merge. CI has not run on any of this work,
because it starts only on pull requests and pushes to `main`. Suite at wrap:
`523 passed` on Python 3.12. Release line: canonical version 0.3.0, the three
carriers agree, latest tag `v0.2.0`, two entries unreleased; the carriers are
ahead of the tag on purpose (decision row 2). Decision row 1. From here
on, every session that changes files ends with a session-wrap: evidence summary
verified against the diff, then a progress entry, decision rows, and a ticket
sweep, then the commit.

**2026-11-25: `config-history` plugin for Claude Code, with zero-setup local history and auto-save (offline, code + tests + docs; one PyPI download per install). 🟡 PARTIAL [unreleased]**
Trigger: the owner wants to publish the tool for people whose settings change
and who want to go back, and asked whether a plugin could alert on changes.
Done: the repo root is now a plugin (`.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `hooks/hooks.json`, `scripts/`, `bin/`,
`skills/`). A session-start and a session-end hook call a POSIX `sh` launcher
that finds Python 3.9 or later and runs a stdlib-only bootstrap, which keeps a
private virtual environment in the plugin data folder and runs
`python -m claude_cfg session-hook start|end`. The package gained a default
local history (`default_history.py`), auto-save with retention of 50 automatic
versions (`autosave_manager.py`, `snapshot_retention.py`), `save` and `restore`
aliases, `CLAUDE_CFG_HOME`, Python 3.9 support and version 0.3.0. Proof:
`523 passed` on Python 3.12 and `523 passed` on the system Python 3.9.6;
`claude plugin validate .` prints "Validation passed" with one `ICON_MISSING`
warning; a throwaway-home run on 3.9.6 with the data folder at
`~/.claude/plugins/data/` saved a first version of 5 files with nothing from the
plugin's own environment, stayed silent on a cache-only change, and printed
"config-history: saved version 2 (1 file changed: settings.json). Go back with:
config-history restore --point 1" on a settings change; three headless Claude
Code 2.1.332 sessions with `--plugin-dir` loaded the plugin, registered six
skills, ran `/config-history:status` with no permission denial, and showed the
save notice while the model answered that the notice was not in its context. An
independent review found 5 significant problems (the plugin snapshotting its own
1,462-file environment, a failed update destroying the working environment, the
restore skill pre-approving destructive forms, a Windows line-ending bug, time
budgets that did not nest); all are fixed with regression tests. Remains: an
interactive session and a real restore inside a session
(`docs/tickets/plugin-not-tried-in-an-interactive-session.md`), Windows and
Linux (`docs/tickets/plugin-launcher-untested-on-windows-and-linux.md`), the
icon (`docs/tickets/plugin-has-no-icon.md`), the `network` manifest field on
older Claude Code
(`docs/tickets/manifest-network-field-unchecked-on-older-claude-code.md`), build
tools not pinned (`docs/tickets/plugin-install-build-tools-not-pinned.md`), and
publishing itself (not pushed; open question 1). Commits `1bbbd01` (plugin) and
part of `0fc294b` (package side). Decision rows 9 to 14.

**2026-11-25: Encryption, race-safe index, safe restore with undo, status, wider coverage and MCP sync (offline, code + tests + docs). 🟡 PARTIAL [unreleased]**
Trigger: a review of the project against Claude Code's `/rewind` found the two
do not overlap, and found six defects in 0.2.0: a comment claiming snapshots
were "safe for public backends" while `settings.json` travels unencrypted, a
`pull` that never removes stale files, a pre-pull backup that copied caches and
`.git` folders with no way to restore it, an unlocked read-modify-write of
`index.json`, missing config files in the tracked list, and no preview before a
pull. Done: passphrase encryption (scrypt + AES-256-GCM, envelope magic
`CCFGENC2`), a passphrase check against existing snapshots, snapshot objects as
the source of truth with `index.json` as a cache, `delete` on every provider,
manifest schema v4 with per-file hashes, `pull --dry-run`, `diff`,
`pull --exact`, backups holding only affected files, `undo`, `status`,
`keybindings.json`, `themes/`, `rules/`, `output-styles/` and `workflows/` in
the defaults, `CLAUDE_CONFIG_DIR` support, opt-in MCP server sync through the
`claude mcp` CLI, `integrate install`, and the CLI split from one 343-line file
into a package. Proof: the suite went from `48 passed` on 0.2.0 to `353 passed`
at the end of this unit; end-to-end runs in throwaway homes covered
encrypted push, a second machine pulling with path rewriting, exact pull, undo,
a planted plaintext snapshot being refused under both names, and a wrong
passphrase being refused. An independent review reproduced 8 significant
problems in the first build (among them: on a case-insensitive disk an exact
pull wrote a file and then deleted it; a plain zip under a `.zip.enc` name
restored with no passphrase) and 2 more in the first fix pass; all were fixed
with regression tests, and the reviewer ran 150 rounds of three concurrent
pushers with no duplicate or lost snapshot. Remains: the second fix pass had no
independent review of its own
(`docs/tickets/last-fix-passes-not-independently-reviewed.md`); S3, R2, SFTP and
Gist and the real `claude mcp` command were exercised with mocks only
(`docs/tickets/remote-backends-and-mcp-cli-exercised-with-mocks-only.md`); an
MCP command that fails during `undo` still marks that part done
(`docs/tickets/undo-marks-mcp-part-done-when-a-command-fails.md`). Commit
`0fc294b`, docs in `461efef`. Decision rows 2 to 8.
