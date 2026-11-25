# claude-cfg

> A versioned history of your [Claude Code](https://claude.com/claude-code) settings, so you can go back to an earlier version. Ships as a Claude Code plugin (`config-history`) and as a CLI (`claude-cfg`) that can also sync the history between machines.

[![CI](https://github.com/razamit/config-history/actions/workflows/ci.yml/badge.svg)](https://github.com/razamit/config-history/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/claude-cfg.svg)](https://pypi.org/project/claude-cfg/)
[![Python versions](https://img.shields.io/pypi/pyversions/claude-cfg.svg)](https://pypi.org/project/claude-cfg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Your Claude Code settings, skills, commands and instructions change over time. Sometimes you change them, sometimes a tool does, sometimes it is an accident. Claude Code keeps no history of those files, so when something breaks there is nothing to go back to.

The `config-history` plugin fixes that. It saves a new version of your config whenever a session starts or ends and something changed, and it gives you commands to see what changed and to go back. It needs no setup and keeps the history on your machine.

- [Install the plugin](#install-the-plugin)
- [What it does](#what-it-does)
- [Go back to an earlier version](#go-back-to-an-earlier-version)
- [What the plugin runs](#what-the-plugin-runs)
- [What gets tracked](#what-gets-tracked)
- [Sync between machines (optional)](#sync-between-machines-optional)

---

## Install the plugin

```bash
claude plugin marketplace add razamit/config-history
claude plugin install config-history@razamit
```

Inside a Claude Code session, the same two steps are `/plugin marketplace add razamit/config-history` and `/plugin install config-history@razamit`.

**Requirement:** Python 3.9 or later on your machine. macOS ships 3.9, so a Mac needs nothing extra. If the plugin finds no suitable Python, it shows a notice at session start and stays inactive.

**There is no setup step.** The first time a session starts with the plugin enabled, it builds a private Python environment in the plugin's own data folder, in the background, using the Python already on your machine. It shows one line, "config-history is setting up for first use (about a minute)", and does not hold the session up. When the build finishes it saves your first version. Nothing is installed into your global Python packages.

The build needs an internet connection once. It installs the tool's three dependencies (`typer`, `rich` and `cryptography`) from PyPI, and it does the same again after a plugin update. After that the plugin works offline.

Tested on macOS so far. See [PORTABILITY.md](PORTABILITY.md) for what that means for Windows and Linux.

---

## What it does

At the start and at the end of a Claude Code session, the plugin compares your tracked config files with the last saved version. If something changed, it saves a new version. If nothing changed, it does nothing and shows nothing.

When a save happens at session start, you see one line:

```
config-history: saved version 2 (2 files changed: settings.json, skills/demo/SKILL.md). To go back, type /config-history:restore
```

The notice goes to you and does not enter Claude's context. We checked this in a test session. A save at session end shows nothing.

- **Where the history lives:** `~/.claude-cfg/history/`, in a folder only you can read (mode 700, files 600 on macOS and Linux). It is local and not encrypted by default.
- **How many versions are kept:** the newest 50 automatic versions. When a new one is saved, the oldest automatic ones beyond 50 are deleted. A version you save yourself (ask Claude to "save my settings as before cleanup", or type `/config-history:history save before cleanup`) is never deleted. To keep a different number, ask Claude to run `config-history config autosave --keep 100`, for example.
- **What is tracked:** `settings.json`, `CLAUDE.md`, and your `commands/`, `skills/`, `agents/`, `plugins/`, `themes/`, `rules/`, `output-styles/` and `workflows/` folders, plus `keybindings.json`. See [What gets tracked](#what-gets-tracked) for the full rules and what is never captured.

---

## Go back to an earlier version

There is one thing to remember: type `/config-history:restore`, with nothing after it.

1. It lists your recent versions in plain words, such as `3  2 hours ago (today 18:11)  settings.json changed`, and asks which one you want. You can also name it up front: `/config-history:restore 3`, or `/config-history:restore before the model change`, and Claude picks the matching version and tells you which one it picked.
2. It shows what going back would change: which files it would create or overwrite. Nothing is written yet.
3. If more than one file would change, it asks whether you want all of them back or only some. Say "only settings.json" to restore that one file and leave the rest as they are.
4. It shows the version it picked (number, when it was saved, what changed) and the files that will change, and asks you to confirm. It restores only after a clear yes; anything else means nothing is restored. Claude Code's permission prompt for the restore is a second check on top of that. Files it replaces are copied to `~/.claude-cfg/backups/` before anything is written.
5. Restart Claude Code so the restored settings load.
6. If it was a mistake, type `/config-history:undo` and restart again. Claude Code asks for permission before the undo runs, since it changes files.

You can also ask Claude in plain words, such as "what changed in my settings since yesterday?" or "my statusline stopped working, what changed?". Claude can answer from the saved versions on its own, through the `history` skill, which only reads the history and can save a new version when you ask it to. It never restores anything: for that it points you to `/config-history:restore`.

The plugin has three skills:

| Skill | What it does |
| ----- | ------------ |
| `/config-history:restore [version or description]` | Walks you through going back: pick a version, see what would change, restore all of it or only some files |
| `/config-history:undo` | Reverts the last restore |
| `/config-history:history [question]` | Answers questions about the history, lists versions, and saves one when you ask. Claude may also use it by itself when you ask what changed |

`restore` and `undo` run only when you type them. Nothing that changes your config runs without a permission prompt: listing versions, comparing and the restore preview do not ask, the real restore and the undo always do. The `history` skill runs `history`, `list`, `diff`, `status` and `save` without a prompt only exactly as written; with anything after them, such as a save label or `--limit 30`, Claude Code asks first. When Claude starts the `history` skill by itself from a plain question, Claude Code asks once whether to run the skill; typing `/config-history:history` does not ask.

A normal restore writes the files in that version and leaves any other tracked files alone. If you also want to delete tracked files that the version does not have, say so (for example "restore version 1 and remove files that are not in it"). Claude then shows the files it would delete and asks you to confirm them before anything runs.

A partial restore, of only some files, does not mark your config as matching that version, because it does not. The next automatic save records the mix as a new version, so you can still go back to how things were before.

The plugin also puts a `config-history` command on the `PATH` of Claude's shell while it is enabled. The skills call it. It is available to Claude's shell, not to your own terminal, which is why the notice and the messages name the slash commands. To use the same functions from a terminal, install the CLI (see [Sync between machines](#sync-between-machines-optional)), where the command is `claude-cfg`.

Credentials are never captured, so a restore does not change your sign-in.

---

## What the plugin runs

Claude Code's install screen tells you that a plugin has hooks. It does not tell you what they run. This section does.

**The two hooks.** The plugin's `hooks/hooks.json` defines two command hooks. Both run a small shell script, `scripts/config-history-hook.sh`, from the plugin folder.

- **SessionStart** (only when a session starts fresh, with a 15 second timeout): runs `config-history-hook.sh start`.
- **SessionEnd** (30 second timeout): runs `config-history-hook.sh end`. It starts the save in the background so closing Claude Code is not delayed.

**What the script does.** It looks for a Python 3.9 or later (`python3.13` down to `python3.9`, then `python3` and `python`) and runs the plugin's bootstrap script with it, ignoring `PYTHONPATH` and user site packages. It skips the macOS `/usr/bin/python3` stub when the command line tools are not installed, so it never triggers an installer dialog. It always exits 0, so a failure can never block a session.

The bootstrap does one of two things:

- If the private environment is built and matches this plugin version, it runs `python -m claude_cfg session-hook start` (or `end`) from that environment. This is the save described above.
- If not, it starts the environment build in the background and shows one notice. The build copies the plugin's own folder to a temporary folder, creates a new virtual environment beside the current one, installs the package from that copy with `pip` (or `uv` when it is on your `PATH`), then deletes the temporary copy. The install uses the exact dependency versions in `scripts/plugin-constraints.txt`, which are updated with each release. After a plugin update the existing environment keeps saving until the new one is ready, and the switch happens only after a successful build. A failed build is deleted and logged, retried after an hour (then 2, 4 and so on, up to once a day), and reported at most once a day.

**What it reads.** The tracked files under `~/.claude` (or the folder `CLAUDE_CONFIG_DIR` names): the list in [What gets tracked](#what-gets-tracked), plus any file under `~/.claude` that a tracked file refers to, such as a status-line script. It hashes them to see whether anything changed. It does not read your prompts, your conversations or your project files. The `projects/` folder, where Claude Code keeps transcripts, is excluded.

**What it writes, and where.**

- `~/.claude-cfg/history/`: the saved versions, one zip file per version, plus an `index.json`.
- `~/.claude-cfg/config.json`, `state.json` and `autosave.lock`: the tool's settings (written on first run), a record of the last saved version with file hashes, and a lock so two sessions never save at once.
- `~/.claude-cfg/plugin-python`: a one-line file holding the path of the private environment's Python, which the `config-history` command reads.
- `~/.claude-cfg/backups/`: copies of the files a restore replaces, kept for the newest 10 restores. Written only when you restore.
- The plugin's data folder (Claude Code sets its path in `CLAUDE_PLUGIN_DATA`): the private environment, and a small install marker, lock, status file and `install.log`. The log holds the output of the environment build.

The plugin does not edit your `settings.json`. Apart from its own data folder, it does not write into `~/.claude` except when you restore. If `CLAUDE_CFG_HOME` is set, it uses that folder in place of `~/.claude-cfg`.

**What leaves your machine.** Nothing, unless you set up a sync backend. The one exception is the environment build above, which downloads packages from PyPI. If you do run `claude-cfg init` to choose a backend, session start also checks that backend for a newer snapshot (with a 3 second limit), and auto-save, if you turn it on, uploads to it. See [Sync between machines](#sync-between-machines-optional).

**What is never captured.** `.credentials.json` (your Claude sign-in), `.claude.json`, `projects/`, `todos/`, `statsig/`, `shell-snapshots/`, `ide/`, `logs/`, `*.log` files, and any `.git`, `node_modules` or `__pycache__` folder. Under `plugins/` only `installed_plugins.json` and `known_marketplaces.json` are captured, so plugin caches, marketplace clones and each plugin's data folder (including this plugin's private environment) are not. MCP server definitions are not captured unless you turn on MCP sync, which is off by default.

**One thing to know about `settings.json`.** The history keeps copies of it as it is. If it holds an API key or a token, copies of that key are in the history folder. The folder is readable only by you and the copies are not encrypted. See [SECURITY.md](SECURITY.md).

### Turn auto-save off

Ask Claude to run `config-history config autosave --disable`, or open `~/.claude-cfg/config.json` and set `"enabled": false` inside the `autosave` section. Turn it back on with `--enable`.

With auto-save off, nothing is saved at session end, and the start hook shows a reminder when tracked files changed since the last version. It does not save. You can still save by hand: ask Claude to save your settings, or type `/config-history:history save`. To stop the hooks running at all, disable the plugin in `/plugin`.

### Uninstall

1. Uninstall the plugin from `/plugin`, or run `claude plugin uninstall config-history@razamit`. To remove the marketplace entry too, run `claude plugin marketplace remove razamit`.
2. Delete `~/.claude-cfg/history/` to remove the saved versions. If you do not use the `claude-cfg` CLI, delete the whole `~/.claude-cfg/` folder instead. It also holds the config, the sync state, restore backups and the `plugin-python` file.
3. Delete the plugin's data folder if it is still there after the uninstall. It holds the private environment. It is normally under `~/.claude/plugins/data/`.

Uninstalling the plugin does not delete your saved versions. They are outside the plugin's folders.

---

## What gets tracked

The plugin and the CLI use the same list. By default:

```
settings.json
CLAUDE.md
commands/
skills/
agents/
plugins/
keybindings.json
themes/
rules/
output-styles/
workflows/
```

You can override this during `claude-cfg init` or by editing the `tracked` list in `~/.claude-cfg/config.json`. If your setup is older than a default entry, `claude-cfg config track-defaults` adds the missing ones. After a push, `claude-cfg` prints a hint when a default entry exists on disk but is not tracked yet.

On push, `claude-cfg` also scans tracked files for references to files under `~/.claude/` and includes any that exist. This covers `~/.claude/<path>`, `${CLAUDE_HOME}/<path>` and absolute paths, so status-line scripts and externalized hook scripts travel with the snapshot.

If you set `CLAUDE_CONFIG_DIR` to an absolute path, `claude-cfg` uses that folder instead of `~/.claude/`. A relative value is ignored. `claude-cfg`'s own files stay in `~/.claude-cfg/` either way, unless `CLAUDE_CFG_HOME` points them elsewhere.

### Never captured

These are skipped even inside a tracked folder, and are never listed, compared or deleted on restore:

- `.credentials.json`, `.claude.json` and its backups, `.DS_Store`, `Thumbs.db` and any `*.log` file
- the top-level folders `projects/`, `todos/`, `statsig/`, `shell-snapshots/`, `ide/` and `logs/`
- any `.git`, `node_modules` or `__pycache__` folder
- everything under `plugins/` except `plugins/installed_plugins.json` and `plugins/known_marketplaces.json`: caches, marketplace clones, the catalog and blocklist files, `plugins/store/` and each plugin's data folder under `plugins/data/`
- `skills/synced/` and `skills/.trash/`

Claude Code rewrites `plugins/known_marketplaces.json` on its own when it refreshes a marketplace. It is still captured, and `status` lists it, but a change to it alone does not trigger an automatic save or a "changes not saved" notice.

Credentials never sync. After restoring a snapshot taken on another machine, run `claude` and sign in again; the restore summary reminds you.

> **Security note**
>
> The exclusion list keeps snapshots small and keeps your Claude login file out. It does not make a snapshot safe to share. `settings.json` can hold API keys and tokens, and `claude-cfg` does not scan or redact file contents. If you turn on MCP server sync, MCP definitions with their tokens go in too.
>
> Encryption is available and recommended: see below. With it off, snapshots are plain zips. The plugin's local history is like that by default: owner-only on your machine, not encrypted. For a sync backend, push only to one that only you can read (your own bucket, a Gist, an SSH server you own). Never use a public bucket.
>
> The `sftp` backend uses trust-on-first-use for host keys. That is fine for hosts you own on trusted networks, but the first connection can be intercepted on a hostile one.

---

---

## Sync between machines (optional)

The plugin keeps its history on one machine. To keep the same Claude Code setup on several machines, use the `claude-cfg` CLI to sync the snapshots to a storage backend of your choice: a folder in Dropbox, OneDrive or iCloud, Cloudflare R2, AWS S3, a GitHub Gist or an SFTP server. Save on one machine, restore on another, and your setup follows you. Snapshots can be encrypted with a passphrase before they leave your machine.

The CLI and the plugin share one engine and one folder, `~/.claude-cfg/`. The CLI also works on its own, without the plugin.

**What `init` changes.** Without `init`, the CLI behaves like the plugin: versions go to the local history and auto-save is on. `claude-cfg init` replaces that with a backend you pick. It leaves auto-save off, because saving to a shared backend on every change should be your call. Turn it on with `claude-cfg config autosave --enable`. The local history you had stays where it is; `init` tells you so, and to keep adding to it, choose the `local` backend and enter that folder (`~/.claude-cfg/history`).

With a backend set up, the session-start hook also checks it. If the backend has a snapshot newer than this machine's last sync, it prints a notice, and it holds auto-save until you run `restore` or `save`, so a new automatic version never buries the newer snapshot. If you turn auto-save on for a backend, the oldest automatic versions are deleted from it once there are more than 50 (change that with `config autosave --keep`). Versions saved by hand are never deleted.

### Features

- **Versioned snapshots:** every save gets an incrementing ID, a timestamp and a message.
- **Auto-save:** a version is saved at session start and end when something changed. On by default for the local history, off for a backend you chose with `init`.
- **Optional encryption:** snapshots can be encrypted with a passphrase before they leave your machine. `init` offers it and recommends it.
- **Multiple backends:** Cloudflare R2, AWS S3, a local folder (Dropbox, OneDrive, iCloud), GitHub Gist, SFTP.
- **Cross-OS restore:** home paths and the `python` launcher are rewritten for the machine you restore on.
- **Safe restores:** preview with `restore --dry-run` or `diff`, back up what a restore replaces, and revert it with `undo`.
- **Status:** `status` tells you what changed here and whether the backend has something newer.
- **MCP servers (opt-in):** user-scope MCP servers can travel with your snapshots.
- **Claude Code integration (opt-in):** `integrate` installs the session hooks and a `/cfg-push` skill for people who use the CLI without the plugin.
- **Auto-discovery:** referenced scripts are picked up automatically.
- **No daemon, no server:** nothing runs between sessions.

### Install the CLI

```bash
pip install claude-cfg
```

To enable a remote backend, install the matching extra:

```bash
pip install "claude-cfg[s3]"     # AWS S3 / Cloudflare R2
pip install "claude-cfg[gist]"   # GitHub Gist
pip install "claude-cfg[sftp]"   # SFTP
pip install "claude-cfg[all]"    # everything
```

Requires Python 3.9 or later.

### Quick start

```bash
# 1. Configure interactively: backend, credentials, tracked files, encryption
claude-cfg init

# 2. Save your current config (init offers to do this for you)
claude-cfg save "initial setup"

# On another machine, after running `claude-cfg init` with the same backend:
claude-cfg restore --dry-run  # see what a restore would change
claude-cfg restore            # restore the latest snapshot
claude-cfg list               # see all snapshots
claude-cfg restore --point 3  # restore a specific snapshot
```

`save` and `restore` are the same as `push` and `pull`. The rest of this README uses `push` and `pull`; either spelling works.

`init` asks which backend to use and tests the connection. It then asks whether to encrypt snapshots (the default is yes), whether to save the passphrase locally, and whether to sync MCP servers. If the backend already holds snapshots, it offers to restore one instead of pushing this machine.

### Commands

| Command | What it does |
| ------- | ------------ |
| `claude-cfg init` | Optional setup: pick a backend, choose encryption, save config, then push the first snapshot or restore an existing one |
| `claude-cfg push [message]` (alias `save`) | Snapshot the current `~/.claude/` and store it |
| `claude-cfg list [--limit N] [--keys]` (alias `history`) | Show the snapshots, newest first. For a sync backend: ID, time, message, machine and whether each is encrypted. For the local history (and in the plugin): Version, When and What changed, 10 at a time. `--limit N` shows at most N and the list says how many older ones exist. `--keys` adds the object key |
| `claude-cfg pull [--point N] [--key KEY]` (alias `restore`) | Restore the latest snapshot, snapshot `#N`, or the one with an exact object key |
| `claude-cfg pull --dry-run` | Show what a pull would change and write nothing |
| `claude-cfg pull --exact [--yes]` | Also delete tracked local files that the snapshot does not have. Asks first; `--yes` skips the question |
| `claude-cfg pull --only PATH` | Restore only this file or folder of the snapshot, such as `--only settings.json --only skills/demo/`. Repeatable. Cannot be combined with `--exact` |
| `claude-cfg diff [--point N] [--key KEY]` | Compare `~/.claude/` with a snapshot (the latest by default). Writes nothing |
| `claude-cfg pull --allow-plain`, `diff --allow-plain` | Accept a snapshot that is not encrypted while encryption is on here, such as one pushed before you turned it on |
| `claude-cfg undo [--force] [--files-only]` | Revert the most recent pull that has not been undone |
| `claude-cfg status [--offline]` | Show local changes since the last push or pull, and whether the backend has a newer snapshot |
| `claude-cfg autosave` | Save a new version now if anything changed since the last one. Never prompts |
| `claude-cfg config show` | Print the current config (credentials and the passphrase are masked) |
| `claude-cfg config set K V` | Update a config value, e.g. `claude-cfg config set r2.bucket my-bucket` |
| `claude-cfg config encrypt` | Turn on passphrase encryption for future pushes |
| `claude-cfg config track-defaults` | Add default tracked entries that an older setup is missing |
| `claude-cfg config mcp [--enable\|--disable]` | Show, enable or disable MCP server sync |
| `claude-cfg config autosave [--enable\|--disable] [--keep N]` | Show, enable or disable auto-save, and set how many automatic versions to keep (default 50) |
| `claude-cfg integrate install\|remove\|status` | Manage the Claude Code session hooks and the `/cfg-push` skill |
| `claude-cfg session-hook start\|end` | What the session hooks run. They never prompt and always exit 0. You do not need to run them yourself |

Errors print as one line with no traceback, because a traceback could show a token or a passphrase. Set `CLAUDE_CFG_DEBUG=1` to see the traceback (code lines only, never variable values) when reporting a bug.

`pull`, `diff`, `undo` and `status` list the first 20 files per group. Pass `--all` to see every file. `--point` and `--key` cannot be combined. `claude-cfg --version` (or `-V`) prints the version. Times are stored in UTC and shown in this machine's time zone, with a relative phrase for recent ones, such as `2 hours ago (today 18:11)` or `yesterday 09:30`.

**Environment variables**

| Variable | Effect |
| -------- | ------ |
| `CLAUDE_CONFIG_DIR` | Use this folder instead of `~/.claude/`. Must be an absolute path |
| `CLAUDE_CFG_HOME` | Use this folder instead of `~/.claude-cfg/` for the config, sync state, backups and the default local history. Must be an absolute path |
| `CLAUDE_CFG_PROGRAM_NAME` | The command name that hints and notices print, such as `config-history`. The plugin sets it. Only a plain name is accepted; anything else is ignored |
| `CLAUDE_CFG_PASSPHRASE` | The snapshot passphrase, for encrypted snapshots |
| `CLAUDE_CFG_DEBUG` | Set to `1` to print a traceback on errors |

---

### Backends

| Backend | Best for                                | Extra to install |
| ------- | --------------------------------------- | ---------------- |
| `local` | Dropbox / OneDrive / iCloud folder      | (built-in)       |
| `r2`    | Cloudflare R2: free egress, S3 API      | `[s3]`           |
| `s3`    | AWS S3                                  | `[s3]`           |
| `gist`  | GitHub Gist (secret, not public)        | `[gist]`         |
| `sftp`  | Any SSH server                          | `[sftp]`         |

The `local` backend is the simplest path: point it at a folder inside Dropbox/OneDrive/iCloud and your snapshots sync to every machine for free. The plugin's default history is also a `local` backend, pointed at `~/.claude-cfg/history`.

A Gist created by `claude-cfg` is secret, not public. GitHub does not list secret Gists, but anyone who has the URL can open one. Encryption is a good idea there.

The Gist backend holds at most about 300 snapshots: the GitHub API lists only the first 300 files of a gist, and each snapshot is one file. Past that, `claude-cfg` stops with an error instead of working from a partial list, and a push to a gist that already holds 300 files is refused before anything is uploaded. Delete old snapshot files from the gist (deleting works on a full gist) or move to another backend. A single snapshot over 10 MB cannot be read through the Gist API either, so a push whose stored file would be larger is refused before upload, with the size and the limit in the message.

---

---

### Encryption

`init` asks whether to encrypt snapshots, and the default answer is yes. If you set up without it, or came from an older version, run:

```bash
claude-cfg config encrypt
```

It asks for a passphrase twice, then asks whether to save it in your local config. Either way it stores a passphrase verifier in the config (`encryption.passphrase_verifier`): a salted scrypt hash that cannot decrypt anything, used only to check a passphrase before a push. A push checks the passphrase against it whether it comes from the prompt, `CLAUDE_CFG_PASSPHRASE` or the saved config, and stops with "This passphrase does not match the one set up on this machine" on a typo. To set a different passphrase, run `claude-cfg config encrypt` again. Before a verifier is stored (by `init`, `config encrypt`, or a push on a machine that has none), the passphrase is tried on the newest encrypted snapshot on the backend. If it does not open it, setup or the push stops with "This passphrase does not open the existing snapshots on this backend", so a second machine set up with a different passphrase cannot push snapshots the others cannot read. A backend that cannot be reached during setup only produces a warning. A pull that decrypts a snapshot on a machine without a verifier stores one. Without a verifier, a prompted push also asks for the passphrase twice. New pushes are encrypted from then on. Snapshots that are already on the backend stay as they are, so any plain snapshot you pushed earlier is still plain. `claude-cfg` has no delete command. It only prunes old automatic versions, see auto-save above. Remove any other old snapshot with your backend's own tools if it held secrets.

**How it works.** The whole snapshot zip is encrypted on your machine with AES-256-GCM, using a key derived from your passphrase with scrypt. Each snapshot gets its own random salt and nonce. GCM also detects tampering. Encrypted objects end in `.zip.enc`.

**Where the passphrase comes from.** `claude-cfg` looks in this order:

1. the `CLAUDE_CFG_PASSPHRASE` environment variable
2. the `encryption.passphrase` value in `~/.claude-cfg/config.json`
3. a hidden prompt, but only when it is running in a terminal

Without any of these it stops with an error that names the environment variable. Empty values count as unset.

**Saving the passphrase.** If you answer yes, the passphrase sits in plain text in `~/.claude-cfg/config.json`. On macOS and Linux that file is readable only by you (mode 600). On Windows it relies on your user profile permissions. Anyone who can read that file and your backend can open your snapshots. If that worries you, answer no and use the environment variable or the prompt.

**Lose the passphrase, lose the snapshots.** There is no recovery. If you set a new passphrase later, snapshots pushed under the old one still need the old one.

**Reading.** Any machine without encryption turned on can read both plain and encrypted snapshots. A machine with encryption on refuses a plain snapshot, so nobody with write access to the backend can slip in an unencrypted one; pass `--allow-plain` to `pull` or `diff` for snapshots pushed before encryption was turned on. An object named `.zip.enc` that is not encrypted is always refused, and an encrypted snapshot whose manifest names a different id than its object key (a swapped or rolled-back object) is refused too. Whether a snapshot is encrypted is read from the file itself, and a passphrase is only requested when an encrypted snapshot is opened. `list` and `status` never ask for one. A plain push prints a one-line note that the snapshot is not encrypted.

**What is still visible with encryption on.** The backend operator can see:

- the number of snapshots, their sizes and their upload times
- snapshot ids and timestamps, which are part of every object name
- a slug of the push message (its first six words) in the object name
- `index.json`, an unencrypted cache that lists each snapshot's id, timestamp, full message, machine name and object key

Do not put anything sensitive in a push message. If `index.json` is lost, the list is rebuilt from the object names. Plain snapshots get their message and machine back from their manifest. Encrypted ones show the message slug and an unknown machine, because reading them would need a passphrase.

Encryption covers the backend only. The files in `~/.claude-cfg/backups/` are plain copies of what a pull replaced.

---

---

### How snapshots are stored

```
<backend root>/
├── index.json                                   # metadata cache
└── snapshots/
    ├── 001_20260507T101530_initial-setup_a3f9c1.zip
    ├── 002_20260507T143022_added-skill_07be4d.zip.enc
    └── ...
```

The objects under `snapshots/` are the source of truth for which snapshots exist. `index.json` is a cache of each snapshot's message and machine name, so the list can show them without opening every snapshot. It can be lost without losing any snapshot.

Each object name is `<id>_<UTC timestamp>_<message slug>_<6 hex characters>`. The random suffix is what lets two machines push at the same moment without overwriting each other. If both pick the same id, the one that sorts later re-uploads under the next free id and removes its first attempt. If two objects ever share an id, `pull` and `diff` ask you to choose one with `--key`; `list --keys` shows the keys.

Each zip contains the tracked files with machine paths replaced by portable tokens, plus a `manifest.json`. The manifest holds the snapshot id, timestamp, message, machine name, source platform, `claude-cfg` version, the tracked list and a hash of every file. It is schema version 4. With MCP sync on, the zip also has `_external/mcp-servers.json`. For an encrypted snapshot, the whole zip, manifest included, is encrypted.

On your machine, `~/.claude-cfg/` holds `config.json`, `state.json` (which snapshot you last pushed or pulled, plus file hashes, used by `status`), `backups/` and, for the default local history, `history/`, which has the same layout as a backend root.

See [PORTABILITY.md](PORTABILITY.md) for how paths and launchers are rewritten.

---

---

### Restoring safely

A restore can preview what it will do, back up what it replaces, and be reverted. The plugin's `/config-history:restore` and `/config-history:undo` use the same machinery. `restore` and `pull` are the same command.

```bash
claude-cfg pull --dry-run    # what would change, nothing written
claude-cfg diff              # compare ~/.claude/ with the latest snapshot
claude-cfg pull              # restore it
claude-cfg undo              # changed your mind: revert that pull
claude-cfg pull --exact      # make the tracked files match the snapshot exactly
claude-cfg pull --point 3 --only settings.json   # restore one file from snapshot #3
```

**Dry run and diff.** Both list what a pull would create, overwrite and delete, and how many files are unchanged. `diff` also names the files that exist only on this machine. Neither writes anything.

**A normal pull** writes the snapshot's files and leaves local files that the snapshot does not have. It tells you how many it kept.

**`--only`.** Restores only the files you name: a file such as `settings.json`, or a folder such as `skills/demo/`, which covers every file under it. Repeat it for more. The plan, the dry run, the backup and `undo` cover only those files. A path that matches nothing in the snapshot stops the pull before anything is written and names the closest matches. Paths with `..` or a leading `/` are refused, and so is a value that starts with `-`, so `--only --dry-run` cannot turn a dry run into a real restore (write `./-name` for a file whose name starts with `-`). Names match the same way as in the rest of the pull, so case is ignored only on a disk that ignores case. MCP servers are never restored by `--only`, and it cannot be combined with `--exact`. A pull with `--only` does not record the snapshot as this machine's last sync, since the machine does not match it afterwards; the next save records the mix as a new snapshot.

**`--exact`.** The snapshot is treated as the whole truth for the tracked folders: local files in them that the snapshot lacks are deleted. It shows the list and asks first, with the default answer no. Pass `--yes` to skip the question. Without a terminal and without `--yes`, the pull stops with an error and changes nothing. Files that are never captured (see above), files outside the tracked paths and files that resolve outside the Claude folder are never deleted. Deletes only happen inside roots that both the snapshot and this machine's config track, so a snapshot cannot widen them. Names are compared ignoring case, Unicode form and trailing dots or spaces, so `skills/Foo/SKILL.md` on disk is the same file as `skills/foo/SKILL.md` in the snapshot and keeps its spelling. With MCP sync on, `--exact` also removes user-scope MCP servers that the snapshot does not list.

**Symlinks and swapped files.** A tracked file that is a symlink pointing outside the Claude folder, such as a `CLAUDE.md` linked from a dotfiles repo, is left untouched and never deleted; the pull lists it as "left untouched, it is a symlink to ...". If a file on this machine sits where the snapshot has a folder, or the reverse, the pull lists those paths and stops before writing anything.

**Backups.** Before a pull writes anything, it copies the files it is about to overwrite or delete into `~/.claude-cfg/backups/<UTC time>/files/`, next to a `backup-manifest.json` that records what the pull did. A pull that changes nothing writes no backup. The newest 10 backups are kept and older ones are removed. Change that with `claude-cfg config set backups.keep 20`.

**`undo`.** Puts back the files the last pull overwrote or deleted, removes the files it created, and restores the record of what you last synced. If you edited any of those files after the pull, `undo` stops and lists them so you do not lose the edits. `claude-cfg undo --force` reverts them anyway. It can undo MCP server changes too. When the pull changed MCP servers and the `claude` checks below fail (for example inside a Claude Code session), `undo` changes nothing and says why. `claude-cfg undo --files-only` puts the files back now and keeps the MCP part of the backup pending; run `claude-cfg undo` from a normal terminal later to put the servers back. A backup with a pending MCP part is never pruned. Backups made by version 0.2 have no record of what the pull changed, so `undo` cannot use them. Their files stay in the folder for you to copy back by hand. `undo` refuses when the pull went into a different Claude folder (another `CLAUDE_CONFIG_DIR`), and it only rewinds the sync record if nothing was pushed or pulled after that pull. Backups keep each file's permissions, and their folders are readable only by you.

---

---

### Status

```bash
claude-cfg status
claude-cfg status --offline
```

`status` compares your tracked files with what they looked like at the last push or pull on this machine, and compares the backend's newest snapshot with the one you last synced. It ends with a suggested next step: push, pull, or run `diff` when both sides changed. `--offline` skips the backend and only checks local changes. Local changes can only be found after at least one push or pull has been recorded on this machine.

---

---

### MCP servers

MCP server sync is off by default. Turn it on with:

```bash
claude-cfg config mcp --enable
claude-cfg config mcp             # show whether it is on
claude-cfg config mcp --disable
```

`init` asks about it too, and suggests yes only when snapshots are encrypted.

**What is synced.** User-scope servers, meaning the `mcpServers` entries in `~/.claude.json` (or in `.claude.json` inside `CLAUDE_CONFIG_DIR` when that is set). Project-scoped and local-scoped servers are not touched. Each definition goes into the snapshot whole, with paths and the `python` launcher tokenized like any other file.

**Secrets.** Definitions often hold API tokens in `env` or in headers, and `claude-cfg` does not strip them. With encryption off they sit in plain text on the backend, so `config mcp --enable` shows a warning and asks for an explicit yes. Turn encryption on first.

**How a pull applies them.** `claude-cfg` never edits `.claude.json`. It runs the `claude` command: `claude mcp add-json <name> - --scope user` with the definition passed on standard input, and `claude mcp remove <name> --scope user`. That means the `claude` CLI must be on your `PATH` when you restore, and it must be version 2.1.327 or later, which is the first that can read a definition from standard input. Claude Code's docs say `add-json` must run outside a Claude Code session, so run a pull that changes MCP servers from a normal terminal, not from inside Claude Code. Before changing any server, `claude-cfg` checks all three; if one fails, it skips the whole MCP step, says why, and still restores the files. If adding a replaced server fails after its old definition was removed, the old definition is put straight back and both outcomes are reported. Server names with characters other than letters, digits, `_`, `.` and `-` are skipped.

A server that is missing here is added, and one whose definition differs is replaced. A server that exists only on this machine is kept, unless you pull with `--exact`. A snapshot with no server list leaves your servers alone. `diff`, `pull --dry-run` and the pull summary print server names only, never definitions. `undo` puts servers back as they were. To make that possible, the backup manifest stores the previous definitions, so it is written readable only by you.

---

---

### Claude Code integration without the plugin

If you use the CLI and not the plugin, `integrate` gives you the same session hooks:

```bash
claude-cfg integrate install
claude-cfg integrate status
claude-cfg integrate remove
```

> **Do not use the plugin and `integrate` together.** Each installs its own session hooks, so both would run at every session start and end. Pick one.

`install` adds three things, and all are optional:

- **A SessionStart hook** in `settings.json` that runs `claude-cfg session-hook start` when a session starts fresh. It auto-saves when auto-save is on and something changed, then prints one line such as "claude-cfg: saved version 2 (2 files changed: settings.json, skills/demo/SKILL.md). Go back with: claude-cfg restore --point 1". With auto-save off, it prints a reminder instead when tracked files changed since the last version. If the backend has a snapshot newer than this machine's last sync, it adds a second line, such as "claude-cfg: snapshot #12 from laptop (2026-07-01 09:30 UTC) is newer than this machine's last sync. Run claude-cfg pull to get it." The notice uses the hook's `systemMessage` field, so you see it and it does not enter Claude's context. We checked this in a test session. The hook never prompts, always exits 0 and gives up quietly if a step is slow.
- **A SessionEnd hook** that runs `claude-cfg session-hook end`. It auto-saves when auto-save is on and prints nothing.
- **A `/cfg-push` skill** at `skills/cfg-push/SKILL.md`. Type `/cfg-push my message` and Claude runs `claude-cfg push "my message"`. Claude cannot invoke it on its own, and it is set up to run only that one command.

`claude-cfg` must be on the `PATH` that Claude Code runs with. `settings.json` and `skills/` are tracked by default, so the next push carries the hooks and the skill to your other machines. Run `claude-cfg integrate install` and then `claude-cfg push`, so the hooks travel with your snapshots. `settings.json` is restored as a whole file, so pulling a snapshot taken before the install removes the hooks; the pull says so when that happens. `remove` takes out only the hook entries and the skill file that `install` wrote. A `cfg-push` skill you wrote yourself is left alone. If an older install added the `claude-cfg status --hook` entry, `install` replaces it and `remove` takes it out.

---

## How this differs from /rewind and from a dotfiles repo

These tools cover different needs, and you can use more than one.

| | Claude Code `/rewind` | `claude-cfg` | Git dotfiles repo |
| --- | --- | --- | --- |
| What it restores | Files Claude changed with its own editing tools in the current session | Your whole tracked config | Whatever you commit |
| What it notices | Only those edits. A change made by a shell command, by hand or by another session is not tracked | Any change, whatever caused it | Any change you commit |
| How long it keeps history | The last 100 checkpoints per session, cleaned up about 30 days after the session's last one | Until you delete the snapshot. Automatic versions are pruned to the newest 50 by default | As long as the repo exists |
| Where it is stored | Locally, under `~/.claude/file-history/` | Your backend, optionally encrypted | Your git remote |
| Across machines | Nothing syncs it | Yes | Yes |
| Across operating systems | No | Rewrites home paths and the `python` launcher | Not by itself |
| Secrets and caches | Not applicable | Built-in exclusion list, optional encryption | You manage `.gitignore` and any secret handling |
| MCP servers | No | Opt-in sync | Not by itself |
| History and diffs | Per-session checkpoints | Snapshot list, `diff` against any snapshot | Full commit history, branches, merges and blame |

The Claude Code docs describe `/rewind` as "not a replacement for version control". It undoes a session's edits. `claude-cfg` works the other way around: it snapshots the whole config, whatever changed it, moves it between machines and keeps it until you delete it.

Against a dotfiles repo, git is better at history, diffs and merging. What `claude-cfg` adds is path and interpreter tokenization across operating systems, an exclusion list for secrets and caches, encryption, and MCP server sync. If you already keep a dotfiles repo and it works for you, keep using it. The two can also run side by side.

---

---

## Upgrading from 0.2 to 0.3

1. **Upgrade every machine before the first push from the new version.** A 0.2 client refuses schema v4 snapshots and cannot read encrypted ones. Run `pip install -U claude-cfg` everywhere first. The new `cryptography` dependency installs on its own.
2. **Your setup keeps working.** The saved config is read as before, older snapshots stay readable, and nothing is encrypted until you run `claude-cfg config encrypt`.
3. **Opt in to what you want.** Run `claude-cfg config encrypt`, `claude-cfg config track-defaults` (adds `keybindings.json`, `themes/`, `rules/`, `output-styles/` and `workflows/`), `claude-cfg config mcp --enable` and `claude-cfg integrate install`, or install the plugin instead of the last one.
4. **`init` is now optional, and auto-save is off after it.** A saved 0.2 config is read as before and is not the automatic local history, so auto-save stays off until you run `claude-cfg config autosave --enable`. `claude-cfg integrate install` now installs a SessionEnd hook as well, and replaces the old `status --hook` entry.
5. **Old backups.** Backups made by 0.2 are full copies and cannot be used by `undo`. They count toward the limit of 10 and are removed with the rest as newer ones arrive.

---

---

## Development

```bash
git clone https://github.com/razamit/config-history.git
cd config-history
pip install -e ".[dev]"
pytest
```

The plugin's tests are `tests/test_plugin_bootstrap.py`, `tests/test_plugin_manifest.py` and `tests/test_plugin_shell.py`. They use fake Python executables and fake command runners, so they build no environment and run no `pip`. See [CONTRIBUTING.md](CONTRIBUTING.md).

Tests run on Python 3.9 to 3.13 across Linux, macOS, and Windows in CI.

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.

---

## License

[MIT](LICENSE) © Amit Razam
