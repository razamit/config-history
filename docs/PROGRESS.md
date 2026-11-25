# Implementation Progress

Newest entry first. One entry per completed unit of work: dated headline,
scope note, status marker (✅ DONE / 🟡 PARTIAL / ⛔ NOT STARTED), proof,
files touched, cross-refs to decisions and tickets. Never rewrite old entries.

---

**2026-11-25: CI green on all 15 jobs for the first time; two real bugs found by the first run on Windows (code + tests + CI config, no spend). ✅ DONE [unreleased]**
Continues the entry below, which ended with the result unknown. After the
workflow fix, run 45671706290 ran the tests everywhere and was red on every
job: Linux `4 failed, 618 passed, 2 skipped`, macOS `5 failed, 619 passed`,
Windows `29 failed, 567 passed, 16 skipped` (30 failed on Python 3.13), and
macOS 3.9 dead in setup (the x64 build of 3.9 cannot load its libraries on the
arm64 runner). The owner chose to fix all of it, Windows included, and allowed
fix commits to be pushed to the pull request branch. An implementer (Opus 5.5)
classified every failure and needed 2 pushes of a budget of 4. Real bugs in
the tool, both fixed in `2309a20`: (1) on Windows a script that
`settings.json` names by its full path was never added to a snapshot, because
the scan read the raw JSON, where backslashes are doubled, and the pattern did
not match them, so a restore elsewhere pointed at a missing file
(`claude_cfg/tracked_files.py`; new regression test in `tests/test_core.py`
that fails without the fix on every system); this scan exists since 0.2.0, so
it gets a line under Fixed in `CHANGELOG.md`; (2) on Windows with Python 3.13
or later the plugin bootstrap stopped treating `CLAUDE_CFG_HOME=/srv/x` as
absolute and fell back to `~/.claude-cfg` while the wrapper still read
`/srv/x`, so the user would have seen "still setting up"
(`scripts/config_history_state.py`, now `posixpath.isabs`; the plugin is
unreleased, so no changelog line). Test assumptions fixed (`985bf02`,
`cf29135`): Typer forces coloured help when `GITHUB_ACTIONS` is set, so four
help tests failed everywhere, fixed once by an autouse fixture in
`tests/conftest.py`; one test asserted the runner's full host name where the
tool caps machine names at 40 characters on purpose; the Windows ones were
hard-coded `/` in expected paths, an unescaped Windows path used as a regex, a
fake environment with `bin/python` where the bootstrap correctly uses
`Scripts\python.exe`, and a backslash path pasted into a JSON string; and
Typer 0.29 prints `[message]` where 0.23 prints `[MESSAGE]`, which appeared
only after the first push. Six tests are now skipped on Windows with a stated
reason (four need `/bin/sh` or the executable bit, two check mode 0o600). CI
config (`cc1b039`): macOS 3.9 runs on `macos-15-intel`; the label was checked
against the `actions/runner-images` README and GitHub's hosted-runner page,
not taken from memory. Proof: run 45678849145 on head `cf29135`, 15 of 15 jobs
pass: Linux `625 passed, 2 skipped`, macOS `627 passed`, Windows
`593 passed, 22 skipped`; locally `627 passed in 20.92s` on Python 3.12 and
`627 passed in 10.90s` on 3.9.6 (624 plus 3 new tests); the pull request
reads MERGEABLE, CLEAN. Honest limits: Windows still never runs the launcher
or the wrapper, since 16 of its 22 skips are `tests/test_plugin_shell.py`
(`docs/tickets/plugin-launcher-untested-on-windows-and-linux.md`, updated; the
Linux half of that ticket is now covered by CI); the two code fixes were read
by the planner and not independently reviewed; the four fix commits carry no
log entry of their own because Windows could only be checked by pushing, so
this commit carries the record. New tickets:
`docs/tickets/ci-tests-newest-typer-while-the-plugin-installs-a-pinned-one.md`,
`docs/tickets/drive-less-tool-home-on-windows-accepted-by-the-plugin-and-refused-by-the-tool.md`.
Decision row 20. Release line unchanged: carriers at 0.3.0, latest tag
`v0.2.0`. Files: commits `2309a20`, `985bf02`, `cc1b039`, `cf29135` touch
`.github/workflows/ci.yml`, `claude_cfg/tracked_files.py`,
`scripts/config_history_state.py`, `tests/conftest.py`,
`tests/mcp_fixtures.py`, `tests/plugin_fakes.py` and
`tests/test_backup_undo.py`, `test_claude_config_dir.py`, `test_core.py`,
`test_mcp_capture_plan.py`, `test_path_matching.py`,
`test_plugin_bootstrap.py`, `test_plugin_shell.py`, `test_restore_plan.py`,
`test_session_hook.py`, `test_status_hook.py`; this commit adds
`CHANGELOG.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, the two new tickets
and the updated launcher ticket.

**2026-11-25: Pull request #8 opened against `main`; CI workflow fixed so the Linux 3.9 job can start (CI config only, no code). 🟡 PARTIAL**
Trigger: the owner asked for the pull request so CI would run on the 0.3.0
work for the first time. The first run (45671228537) failed before any test
ran: "The version '3.9' with architecture 'x64' was not found for Ubuntu
26.04." `ubuntu-latest` is now Ubuntu 26.04, `actions/python-versions` lists
3.9.25 for Linux 22.04 and 24.04 only, and the matrix's default fail-fast
cancelled the other 14 jobs ("The strategy configuration was canceled because
test.ubuntu-latest_3_9 failed"), so that run says nothing about the code on
any platform. Fix, chosen by the owner over dropping 3.9 on Linux: the Linux
3.9 job runs on `ubuntu-24.04`, every other job stays where it was, and
`fail-fast` is off so one job cannot cancel the rest. Proof so far: the
workflow parses and its strategy block holds one exclude
(`ubuntu-latest` + 3.9) and two includes (`ubuntu-24.04` + 3.9, and the
existing macOS x64 one); `git merge-tree origin/main HEAD` still exits 0.
Not known when this entry was written: the result of the run this commit
starts. It is the first time the suite runs on Linux and Windows at all
(`docs/tickets/plugin-launcher-untested-on-windows-and-linux.md`), so
failures there would be new information, not a regression. The next entry
records what it showed. Files: `.github/workflows/ci.yml`, this file.

**2026-11-25: GitHub repository renamed to `razamit/config-history` (docs only in the repo, one change on GitHub, no code). ✅ DONE.**
Carries out decision row 16. The easy-flow commit `700ed85` was pushed while
the repository was still `razamit/claude-cfg`; the rename in GitHub's settings
did not take effect twice (the API kept returning the old name and "Could not
resolve" for the new one), so the owner asked for it to be done from here with
`gh repo rename config-history -R razamit/claude-cfg --yes`. Proof:
`gh repo view razamit/config-history` returns
`{"nameWithOwner":"razamit/config-history","url":"https://github.com/razamit/config-history","visibility":"PUBLIC"}`;
`origin` now reads `https://github.com/razamit/config-history.git` and
`git fetch` leaves the branch in sync at `700ed85`; `git ls-remote` on the old
URL returns the same head, so the redirect works; the CI badge URL answers 200.
Not done and not claimed: the install command in the README still cannot work,
because `.claude-plugin/marketplace.json` is on this branch and missing from
`main` (404). That check waits for the merge and keeps
`docs/tickets/install-command-names-a-repo-that-does-not-exist-yet.md` open
(updated). The owner also decided to keep the `history` skill's exact
pre-approved commands after the live test (decision row 19; no file changed by
it). Files: `docs/PROGRESS.md`, `docs/DECISIONS.md`, the ticket above.

**2026-11-25: Easy flow for the `config-history` plugin: one guided restore command, three skills, plain history, local times, single-file restore (offline, code + tests + docs, no spend). 🟡 PARTIAL [unreleased]**
Trigger: the owner's bar for a newly installed plugin, "it should be super easy
or it won't work", and the choice "Essentials + extras" from the options laid
out. Done: `/config-history:restore` with no arguments is the one command to
remember (lists versions, takes a number or words such as "yesterday",
previews, offers only some files, confirms in the conversation, restores, says
to restart and how to undo); three skills replace six (`restore`, `undo`,
`history`; `save`, `diff` and `status` are deleted), and `history` is the one
skill Claude may start by itself. The CLI gained `restore --only <path>`, a
`history` alias with `--limit` and a three-column list (Version, When, What
changed), times in the local zone with a relative phrase, and messages that
under the plugin name tell the user something they can do. Repo URLs outside
`docs/` now read `razamit/config-history`. An independent review (Fable 5.2)
of the build raised 9 findings, 3 of them important: wildcard pre-approvals in
the model-invocable skill, `--only` swallowing `--dry-run` so a pre-approved
dry run became a real restore (reproduced), and the permission prompt as the
only confirmation. A fix pass (implementer, Opus 5.5) answered findings A to H
plus two from the planner's run, each with a regression test; the new tests
for a created file in a partial undo and for `skills/demo` against
`skills/demo-old/` passed without a code change. Finding I (the remote) is the
owner's and is ticketed. Proof: `624 passed in 20.05s` on Python 3.12 and
`624 passed in 10.99s` on Python 3.9.6, up from `523 passed` at the last entry
(`590` after the build, before the fix pass); `claude plugin validate .` prints
"Validation passed with warnings" (`ICON_MISSING` only); no em dash outside
`docs/`; `git grep -n "razamit/claude-cfg" -- . ':!docs'` prints nothing. A
throwaway-home run under the plugin name after the fix pass: a save printed
"Version 1 saved just now (today 19:34), 2 files, 0.8 KB" with no encryption
notice; `history` printed the three-column table with a label as
`"after model change" (saved by you)`;
`restore --point 1 --only settings.json --only --dry-run` exited 1 with
"--only needs a path after it, but got '--dry-run', which looks like an
option. Nothing was restored." and the same file checksum before and after;
`restore --dry-run --point 1 --only settings.json` printed the plan and
"Dry run: nothing was written."; the real partial restore reported
"0 created, 1 overwritten" and "Type `/config-history:undo` to revert this
restore"; `undo` put the file back byte for byte. Five headless sessions the
owner approved (Claude Code 2.1.332, Haiku, default permission mode, the real
`~/.claude` login, tool data in a scratch folder deleted afterwards): a
throwaway probe skill with the rule `Bash(echo probe *)` ran `echo probe plain`
and was refused for `"$(...)"`, bare `$(...)`, backticks and `; other-command`,
so substitution under a wildcard rule does not run unprompted
(`docs/tickets/command-substitution-under-wildcard-allow-rules-not-tested-live.md`,
filed and closed today); the plugin registered its three skills; asked "what
changed in my settings?" with no command, Claude's first call was the
`config-history:history` skill, which Claude Code then held for the user's
approval (a skill Claude starts by itself asks once; `README.md` now says so);
typed as `/config-history:history ...`, it ran `config-history history` and
`config-history status` with no permission denial. Remains, and why this is
partial: the guided restore flow and its confirmation in the conversation,
`/config-history:undo`, the on-screen notice and the save at session end have
not been seen in a real session and are skill text and tests on that text
(`docs/tickets/plugin-not-tried-in-an-interactive-session.md`, updated twice);
the fix pass was not independently reviewed
(`docs/tickets/last-fix-passes-not-independently-reviewed.md`, updated); the
repository is not renamed on GitHub yet, so the README's install command does
not resolve and `CHANGELOG.md` says "was renamed" ahead of the fact
(`docs/tickets/install-command-names-a-repo-that-does-not-exist-yet.md`); a
few sync-backend messages still name a command the user cannot type
(`docs/tickets/some-plugin-hints-still-name-commands-the-user-cannot-type.md`);
no view of what changed inside a file
(`docs/tickets/no-line-by-line-view-of-what-changed-inside-a-file.md`, open
question 4). Changelog: the bullets for this work are already under
`## [Unreleased]` in `CHANGELOG.md`, written with the code. Release line
unchanged: carriers at 0.3.0, latest tag `v0.2.0`. Not committed at the time
of writing. Files (53 paths): 26 under `claude_cfg/` (new: `change_summary.py`,
`restore_selection.py`, `time_display.py`, `cli/history_output.py`; changed:
`backup_manager.py`, `command_wording.py`, `core.py`, `errors.py`,
`passphrase.py`, `program_name.py`, `pull_manager.py`, `pull_summary.py`,
`restore_plan.py`, `session_hook_lines.py`, `session_hook_manager.py`,
`snapshot_selection.py`, `snapshot_store.py`, `undo_manager.py`, and in `cli/`
`app.py`, `autosave_commands.py`, `mcp_prompts.py`, `output.py`,
`restore_commands.py`, `restore_output.py`, `snapshot_commands.py`,
`status_output.py`); 7 under `tests/` (new: `test_command_hints.py`,
`test_history_list.py`, `test_partial_restore.py`, `test_time_display.py`;
changed: `test_local_wording.py`, `test_plugin_manifest.py`,
`test_session_hook.py`); `skills/history/SKILL.md` and
`skills/restore/SKILL.md` changed, `skills/save/SKILL.md`,
`skills/diff/SKILL.md` and `skills/status/SKILL.md` deleted; `README.md`,
`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml`,
`.claude-plugin/plugin.json`, `.github/ISSUE_TEMPLATE/config.yml`; and under
`docs/` this file, `DECISIONS.md`, four new tickets and two updated ones.
Decision rows 15 to 18.

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
