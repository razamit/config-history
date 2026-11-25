# claude-cfg: Portability and Restore

This file describes the layer above storage: what gets captured, how it is made platform-neutral, and how it is restored on Windows, macOS, Linux or WSL. Storage itself (backends, object names, the index, encryption) is covered in [README.md](README.md). The last section lists ideas from the original design that are not built.

---

## 1. Core principle

`claude-cfg` never copies the whole `~/.claude/` folder. It captures the paths on an explicit tracked list, skips a fixed set of secrets and machine state, rewrites machine-bound paths into tokens, and reverses that on restore.

Capture: **list tracked files, drop excluded ones, tokenize.**
Restore: **fetch (decrypt if needed), plan, back up, write, expand tokens.**

If `CLAUDE_CONFIG_DIR` is set to an absolute path, it replaces `~/.claude/` everywhere in this file, and `.claude.json` is read from inside it.

`CLAUDE_CFG_HOME`, also an absolute path only, moves the tool's own folder (`~/.claude-cfg/`: the config, sync state, pull backups and the default local history) somewhere else. A relative value is ignored.

The tool runs on Python 3.9 or later. CI runs it on 3.9 to 3.13 on Linux, macOS and Windows.

---

## 2. What is captured

### The tracked list

Defaults:

```
settings.json    CLAUDE.md     commands/     skills/      agents/
plugins/         keybindings.json            themes/      rules/
output-styles/   workflows/
```

The list is saved in the config at `init` and can be edited. `claude-cfg config track-defaults` adds defaults that an older list lacks. On push, files under `~/.claude/` that a tracked file refers to (as `~/.claude/<path>`, `${CLAUDE_HOME}/<path>` or an absolute path) are added too, so externalized hook and status-line scripts travel. References that resolve outside the Claude folder are ignored.

`settings.local.json` is not in the defaults. Add it yourself if you want local overrides to travel.

### How each file is treated

| File | On capture | On restore |
|---|---|---|
| JSON file | Every string value is tokenized (paths, then the python launcher). The file is rewritten only if something changed | Tokens are expanded in every string value |
| Other text file | Machine paths are replaced with tokens | Tokens are expanded |
| Binary file (a null byte or invalid UTF-8) | Copied as is | Written as is |
| `_external/mcp-servers.json` (only with MCP sync on) | Servers from `.claude.json`, tokenized like a JSON file | Applied through `claude mcp`, see section 6 |

### Never captured

Never captured, even inside a tracked folder. This list is fixed in code and cannot be changed in the config:

```
.credentials.json, .claude.json, .claude.json.backup*, .DS_Store, Thumbs.db, *.log
projects/  todos/  statsig/  shell-snapshots/  ide/  logs/     (top-level folders)
.git/  node_modules/  __pycache__/                              (anywhere)
plugins/* except plugins/installed_plugins.json and plugins/known_marketplaces.json
skills/synced/  skills/.trash/
```

The same filter guards restore, so a path in this list is never listed as a local extra and never deleted by `pull --exact`. The `_external/` folder name is reserved for non-file members and is skipped by all file handling.

---

## 3. Path tokenization

Three tokens, expanded at restore time against the machine doing the restore.

| Token | Meaning |
|---|---|
| `${HOME}` | The user's home directory |
| `${CLAUDE_HOME}` | The Claude folder (`~/.claude`, or `CLAUDE_CONFIG_DIR`) |
| `${PYTHON}` | The python launcher on the target: `python3` if found, then `python`, and `python3` if neither is on `PATH` |

**Capture.** Absolute paths for the Claude folder and the home folder are matched with either separator style, and `~/.claude` is matched too when the Claude folder really is `~/.claude`. The most specific base wins, so a Claude folder inside home becomes `${CLAUDE_HOME}`. The rest of the path is stored with `/` separators. On Windows the match is case-insensitive. A Windows value `C:\Users\amit\.claude\hooks\guard.py` is stored as `${CLAUDE_HOME}/hooks/guard.py`.

A leading bare launcher (`python`, `python3`, `python3.11`, `python.exe`) in a JSON string value becomes `${PYTHON}`, but only when the value is followed by arguments and looks like a command (it has a `.py` file, a path separator or one of the path tokens). Path-qualified interpreters such as `/usr/bin/python3` or a venv path are left alone.

**Restore.** Tokens expand to the target's home and Claude folder. The tail of each path is converted to the target's native separator, backslashes on Windows. `${PYTHON}` becomes the launcher found on the target, which fixes the usual `python` (Windows) against `python3` (macOS and Linux) mismatch.

The code lives in `paths.py` (`collapse_paths`, `expand_paths`, `collapse_interpreter`, `expand_interpreter`) and `content_transform.py`.

---

## 4. settings.json and hooks

`settings.json` is a JSON file, so it follows the rule above: every string value gets path and interpreter tokenization. That covers hook commands and a `statusLine` command. There is no special handling of hooks beyond this.

Anything else in a command is copied as written: absolute binary paths, Windows-only syntax such as `%USERPROFILE%`, `.bat` or `powershell`, and so on. After a restore across operating systems, check any command that did not use paths under the home or Claude folder. The most reliable approach is to keep hook logic in a script under `~/.claude/hooks/`, which syncs with the snapshot, and have the hook command call it.

`claude-cfg integrate install` adds a SessionStart hook (`claude-cfg session-hook start`), a SessionEnd hook (`claude-cfg session-hook end`) and the `/cfg-push` skill. All three sit in tracked paths and travel with the next push. The hook commands start with the bare `claude-cfg` launcher, so `claude-cfg` must be on the `PATH` on every machine you restore to. The `config-history` plugin's hooks live in the plugin, not in `settings.json`, and are not part of a snapshot.

---

## 5. Snapshot manifest (schema v4)

Each zip holds a `manifest.json`:

```json
{
  "schema_version": 4,
  "id": 12,
  "timestamp": "2026-06-09T10:00:00Z",
  "message": "added a skill",
  "machine": "work-laptop",
  "source_platform": "darwin",
  "source_home": "${HOME}",
  "claude_cfg_version": "x.y.z",
  "automatic": false,
  "files": ["CLAUDE.md", "settings.json", "skills/review/SKILL.md"],
  "tracked": ["settings.json", "CLAUDE.md", "commands/", "skills/"],
  "file_hashes": { "CLAUDE.md": "<sha256 of the stored bytes>" },
  "content_hash": "<one hash over every path and hash>"
}
```

`source_platform` is `win32`, `darwin` or `linux`, the same names the restore target uses. Manifests written before this change say `windows`, which is read as `win32`.

Schema history: v1 files and message; v2 adds machine and timestamps; v3 adds the source platform and home tokens; v4 adds the tracked list and file hashes. The `automatic` field marks a version that auto-save made, which retention may delete; it is `false` for a version you save yourself. A manifest without it counts as not automatic. It did not need a new schema version.

A restore refuses a snapshot whose schema is newer than the running tool supports and tells you to upgrade. It reads older ones. Snapshots before v4 have no tracked list, so the tracked list from your local config decides which local files count as extras for `--exact`. For restore decisions the hashes are recomputed from the archive, not taken from the manifest.

---

## 6. MCP servers

Syncing MCP servers is opt-in (`claude-cfg config mcp --enable`). `~/.claude.json` is a sibling file of `~/.claude/` (inside `CLAUDE_CONFIG_DIR` when that is set). It is large and mostly machine-bound, so `claude-cfg` reads only the top-level `mcpServers` map, which holds user-scope servers. Project-scoped servers belong in each repo's `.mcp.json`, and local-scoped ones are not touched.

On capture, each definition is stored whole in `_external/mcp-servers.json`, with paths and the python launcher tokenized. `env` values and headers are **not** stripped or replaced with placeholders, so the snapshot carries any tokens in them. See [SECURITY.md](SECURITY.md).

On restore, `.claude.json` is never written. Each change is a `claude` command:

```
claude mcp add-json <name> - --scope user      (definition on stdin)
claude mcp remove <name> --scope user
```

This needs the `claude` CLI on `PATH`, version 2.1.327 or later, and the pull must run from a normal terminal, outside a Claude Code session, because `add-json` must not run inside one. These are checked first, and the whole MCP step is skipped with a reason when one fails. A replace whose add fails right after its remove puts the previous definition back. A server missing locally is added, one whose definition differs is replaced, and a server only present locally is kept unless the pull used `--exact`. If a command fails, the files are still restored and the failed server names are reported. A snapshot without a server list leaves local servers untouched.

---

## 7. Secrets

- `.credentials.json` is excluded and never enters a snapshot.
- There is no redaction pass. `claude-cfg` does not scan files for tokens, so a key written into `settings.json` or an MCP definition is captured as it is.
- Encryption is the protection for the backend: the whole snapshot zip is encrypted with a passphrase (scrypt and AES-256-GCM). See [SECURITY.md](SECURITY.md) for what stays visible.

Credentials are never synced. A restore of a snapshot taken on another machine ends with a reminder to run `claude` and sign in again.

---

## 8. Capture and restore flow

Push:

```
1. claude_home = CLAUDE_CONFIG_DIR or ~/.claude
2. files = files under the tracked roots + referenced files, minus the exclusions
3. for each file: tokenize (text) or copy (binary), record its sha256
4. with MCP sync on: add _external/mcp-servers.json
5. write manifest.json, build the zip
6. encrypt if encryption is on; name the object <id>_<time>_<slug>_<hex>.zip[.enc]
7. upload, check for an id collision with another machine, update index.json
8. record the push in ~/.claude-cfg/state.json
```

Pull:

```
1. find the snapshot (latest, --point, or --key); fetch it; decrypt if the bytes are encrypted
2. refuse if its schema is newer than this tool supports
3. build a plan: create / overwrite / unchanged / only on this machine
   (a file counts as unchanged if it is equal as written here, or equal once both are tokenized)
   with --exact, only-local files become deletions
4. plan the MCP servers, when MCP sync is on and the snapshot has a server list
5. --dry-run and diff stop here
6. check that every destination is inside the Claude folder
7. back up the files that will be overwritten or deleted (nothing changed: no backup)
8. write files, expanding tokens for this machine; delete for --exact
9. apply MCP changes through the claude CLI
10. record the pull in state.json; prune backups to backups.keep (default 10)
```

`undo` reverses steps 7 to 9 from the backup. When the pull changed MCP servers and step 9 cannot run here, `undo` refuses unless `--files-only` is passed, which reverses steps 7 and 8 and leaves step 9 for a later `undo`.

---

## 9. Platform resolution

| Platform | `.claude` root | Native separator | Re-auth on restore |
|---|---|---|---|
| `win32` | `%USERPROFILE%\.claude`, or `CLAUDE_CONFIG_DIR` | `\` | Yes |
| `darwin` | `~/.claude`, or `CLAUDE_CONFIG_DIR` | `/` | Yes |
| `linux` | `~/.claude`, or `CLAUDE_CONFIG_DIR` | `/` | Yes |
| WSL | `~/.claude` (the Linux home), or `CLAUDE_CONFIG_DIR` | `/` | Yes |

`CLAUDE_CONFIG_DIR` counts only when it is an absolute path. WSL is detected when `platform.uname().release` contains `microsoft`. It is treated as Linux, and a pull prints a note that this home is separate from any Windows-native `~/.claude`.

---

## 10. Merge and conflict policy

- A normal pull overwrites the files that the snapshot contains and leaves other local files alone. Overwritten files are backed up first, and `undo` can bring them back.
- `pull --exact` also deletes tracked local files that the snapshot lacks, after you confirm.
- `.claude.json` is never written by `claude-cfg`. MCP servers are changed by name through the `claude` CLI.
- There is no per-file conflict flag. `diff` and `pull --dry-run` show what would be overwritten, and `status` suggests `diff` when both this machine and the backend have changed.

---

## 11. Edge cases

- **Credentials never sync.** Every restore prompts a re-auth. This is by design.
- **macOS uses the Keychain, not a file.** `claude-cfg` does not touch credentials. Just run `claude` again.
- **Project history is not portable** and is excluded. It is keyed by the local path.
- **Symlinks.** A symlinked file is stored as the file it points to. Symlinked folders inside a tracked folder are not followed. A restore never writes or deletes through a symlink that leaves the Claude folder: such a file (a `CLAUDE.md` linked to a dotfiles repo, say) is left untouched and listed in the pull summary.
- **Large binary assets** inside skills are copied as they are. There is no size guard, except on the Gist backend, which refuses a snapshot it could not serve back (over 10 MB as stored).
- **Names that differ only in case.** A snapshot file is matched to a file on disk by its exact name first. Only when the Claude folder is on a case-insensitive filesystem (checked with a probe file) does `Foo.md` on disk count as the snapshot's `foo.md`. On a case-sensitive disk both names are restored as two files. `straße.md` and `strasse.md` are always two names, and trailing dots and spaces are ignored only on Windows. The exclusion list ignores case on every platform.
- **Mixed Windows-native and WSL** on one machine means two separate `.claude` homes. Treat them as separate machines.

---

## 12. The config-history plugin

The plugin runs the same tool from a private Python environment, so the capture and restore rules above apply to it unchanged. What differs is the launcher.

- **The launcher is a POSIX `sh` script.** `scripts/config-history-hook.sh` and `bin/config-history` need `sh`. The plugin has been tested only on macOS so far. Windows and Linux are untested, and nothing here claims they work. The plugin's unit tests run in CI, but they use fake Python executables and do not build a real environment.
- **Python.** The launcher looks for `python3.13` down to `python3.9`, then `python3` and `python`, and uses the first that is 3.9 or later. macOS ships 3.9. On macOS it skips `/usr/bin/python3` when the command line tools are missing, so it never opens an installer dialog. With no suitable Python the plugin shows a notice and stays inactive.
- **The environment** lives in the plugin's data folder (`CLAUDE_PLUGIN_DATA`). A pointer file, `plugin-python` in the tool's folder, tells `bin/config-history` which Python to run. The bootstrap scripts are standard library only and run on Python 3.9.
- **`CLAUDE_CFG_HOME`** is honored by the launcher, the pointer file and the tool, so one value moves them all.
- **`CLAUDE_CFG_PROGRAM_NAME`** is set to `config-history` for the tool the plugin runs, so notices and hints print the command the user has.

---

## 13. Not built

Ideas from the original design that the code does not do:

- Per-platform hook command variants, a portability linter and `needs_review` flags
- A secret redaction pass with `${ENV:NAME}` placeholders, and `--allow-secrets`
- `include` and `exclude` glob settings and an `--allow-unsafe` override
- `--on-conflict overwrite|merge|skip` and `--no-backup`
- A `doctor` command
