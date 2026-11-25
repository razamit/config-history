# Security Policy

## Supported versions

Only the latest released version of `claude-cfg` receives fixes. The `config-history` plugin is versioned together with it.

| Version         | Supported |
| --------------- | --------- |
| Latest release  | Yes       |
| Earlier         | No        |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Email the maintainer at **razamit23@gmail.com** with:

- A description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- The version of `claude-cfg` or the `config-history` plugin, and your environment

You can expect an initial response within 7 days. Once a fix is ready, a patch release will be published to PyPI and the advisory disclosed in the GitHub Security Advisories tab.

## Scope

In scope:
- Code execution, credential leakage, or path-traversal issues in `claude-cfg` itself
- Insecure handling of snapshots, configs, or backend credentials
- The `config-history` plugin's hooks, launcher scripts and environment build
- Weaknesses in the snapshot encryption (key derivation, cipher use, tampering)

Out of scope:
- Misuse of a backend you control (e.g. a public S3 bucket)
- Issues in upstream dependencies, including `cryptography`. Please report those upstream

## What snapshots contain

Snapshots hold the tracked files under `~/.claude/` (or `CLAUDE_CONFIG_DIR`), with machine paths replaced by portable tokens. `claude-cfg` does not scan or redact file contents.

Never captured, even inside a tracked folder: `.credentials.json`, `.DS_Store`, `Thumbs.db`, `*.log` files, the top-level folders `projects/`, `todos/`, `statsig/`, `shell-snapshots/`, `ide/` and `logs/`, any `.git`, `node_modules` or `__pycache__` folder, `skills/synced/` and `skills/.trash/`, and everything under `plugins/` except `plugins/installed_plugins.json` and `plugins/known_marketplaces.json`. That keeps each plugin's data folder (`plugins/data/<id>/`, where this plugin's private environment lives) out of snapshots, and a restore never writes or deletes there.

That list keeps the Claude login file and machine state out. It does not make a snapshot safe to share. Files such as `settings.json` can hold API keys and tokens, and they are captured as they are.

## The config-history plugin

The plugin runs code on your machine at every Claude Code session start and end, so this is what it does and does not do. The README has the same account in plain words under [What the plugin runs](README.md#what-the-plugin-runs).

- **Two hooks.** `hooks/hooks.json` defines a SessionStart hook (15 second timeout, fresh starts only) and a SessionEnd hook (30 second timeout). Each runs `scripts/config-history-hook.sh`, a POSIX `sh` script that finds a Python 3.9 or later and runs the plugin's bootstrap script with `-B -E -s`, so `PYTHONPATH` and user site packages are ignored. It always exits 0. The plugin does not edit `settings.json`.
- **A private environment.** On the first session, and again after a plugin update, a background process copies the plugin folder to a temporary folder in the plugin's data folder, creates a new virtual environment there beside the one in use, installs the package from the copy with `pip` (or `uv` when it is on `PATH`) and deletes the copy. Nothing goes into the global Python packages. This step downloads `typer`, `rich` and `cryptography`, and their dependencies, from PyPI (`pypi.org` and `files.pythonhosted.org`, declared under `network.hosts` in `plugin.json`). Their versions are pinned exactly in `scripts/plugin-constraints.txt`, updated with each release, so a new release on PyPI does not reach the environment until the pins change. There is no hash pinning, so a replaced file for a pinned version would still be accepted, and the build tools (`setuptools`, `wheel`) are not pinned. The environment in use keeps running until the new one has installed; a failed build is deleted and retried with a growing delay (1 hour, doubling up to 24 hours). The step's output goes to `install.log` in the data folder.
- **What it reads and writes.** It reads the tracked files under `~/.claude` (see "What snapshots contain" below). It writes versions to `~/.claude-cfg/history/`, plus `config.json`, `state.json`, `autosave.lock`, a `plugin-python` pointer file and restore backups under `~/.claude-cfg/`, and its environment and install log to the plugin's data folder. Apart from the plugin's data folder, it writes into `~/.claude` only when you restore a version.
- **A local history that is not encrypted by default.** Each version is a zip that holds copies of `settings.json` and the other tracked files, as they are. If `settings.json` holds an API key or a token, copies of it are in the history, and the plugin does not scan or redact them. On POSIX systems the folders are created `0700` and the files `0600`, so only your user can read them; Windows relies on per-user profile ACLs. A folder that existed beforehand keeps its mode. Anyone who can read your home folder as you, or a backup of it, can read the history. Turn auto-save off if that is not acceptable (see below), and delete `~/.claude-cfg/history/` to remove what was saved.
- **No network use, except the build and a backend you set up.** After the environment is built, the hooks make no network calls unless you ran `claude-cfg init` and chose a remote backend. Then session start checks that backend for a newer snapshot (3 second limit), and auto-save, if you enable it, uploads to it. Protect that backend as described under Encryption.
- **The skills.** The six skills set `disable-model-invocation`, so Claude cannot start them, and each pre-approves only `config-history` commands that change nothing. `/config-history:restore` pre-approves `list` and the dry run only, so the real restore goes through Claude Code's permission prompt after the skill's own confirmation. `/config-history:undo` pre-approves nothing, so it asks too. `save`, `history`, `diff` and `status` run without a prompt. The `config-history` command on Claude's shell is the same tool as `claude-cfg`.
- **Turning it off.** `config-history config autosave --disable` stops saving. Disable or uninstall the plugin to stop the hooks. Uninstalling does not delete `~/.claude-cfg/` or the plugin's data folder; delete them yourself.

If you want an encrypted history, use the CLI: `claude-cfg config encrypt` turns encryption on for new versions. Auto-save then needs the passphrase without a prompt, from `CLAUDE_CFG_PASSPHRASE` or a saved passphrase, and skips a save when neither is available. Session start then shows a notice that says so.

## Encryption

Snapshots can be encrypted with a passphrase before upload: scrypt (N=2^15, r=8, p=1) derives a 256-bit key and AES-256-GCM encrypts the whole snapshot zip, manifest included. Each snapshot gets a fresh random salt and nonce. The envelope is the magic bytes `CCFGENC2`, then the scrypt parameters (log2 N, r, p, one byte each), the 16-byte salt, the 12-byte nonce and the ciphertext. The whole header is authenticated as associated data, and before deriving a key a reader refuses any scrypt parameters other than N from 2^14 to 2^18 with r=8 and p=1, so a hostile object costs at most about 256 MiB to open. After decrypting, the manifest's snapshot id must match the id in the object key, so a swapped or rolled-back object is refused. A machine with encryption on refuses plain snapshots unless `--allow-plain` is passed, and an object named `.zip.enc` without the envelope is always refused. `init` offers encryption and defaults to yes. Existing setups use `claude-cfg config encrypt`. Encryption is recommended for every backend.

What it does not cover:

- **Metadata on the backend.** Object names carry the snapshot id, the timestamp and a slug of the push message (its first six words). `index.json`, a cache that stays unencrypted, lists each snapshot's id, timestamp, full message, machine name and object key. Object sizes and the number of snapshots are visible too. Keep push messages free of secrets.
- **Old snapshots.** Turning encryption on affects future pushes only. Plain snapshots already on the backend stay plain until you remove them with your backend's own tools.
- **Local files.** The backups in `~/.claude-cfg/backups/` are plain copies of files a pull replaced, and the plugin's default history in `~/.claude-cfg/history/` is not encrypted.
- **A lost passphrase.** There is no recovery.

The passphrase is read from the `CLAUDE_CFG_PASSPHRASE` environment variable, then from `encryption.passphrase` in the config file, then from a hidden prompt when running in a terminal. If you choose to save it during setup, it is stored in plain text in `~/.claude-cfg/config.json`. That file is `chmod 600` on POSIX systems and relies on per-user profile ACLs on Windows. Anyone who can read it and your backend can open your snapshots. Do not save the passphrase if that is not acceptable, and use the environment variable or the prompt instead. `config show` masks it. `init` and `config encrypt` also store `encryption.passphrase_verifier`, a salted scrypt hash under its own label, at the same scrypt cost as a snapshot, that cannot decrypt a snapshot. Push checks the passphrase against it whatever its source (prompt, environment or config), so a typo cannot produce a snapshot nobody can open. Before a verifier is stored, by `init`, `config encrypt` or a push on a machine without one, the passphrase must open the newest encrypted snapshot on the backend, if there is one. A pull that decrypts a snapshot on a machine without a verifier stores one.

## MCP servers

MCP server sync is off by default. When enabled, user-scope servers from `.claude.json` are stored in the snapshot as `_external/mcp-servers.json`. `claude-cfg` does not strip `env` values or headers, and definitions often hold API tokens, so with encryption off they sit in plain text on the backend. Enabling the sync without encryption asks for an explicit confirmation. `claude-cfg` only reads `.claude.json`. Changes are made through `claude mcp add-json` and `claude mcp remove`, with the definition passed on standard input so it never appears in a process argument list or an error message. A pull backup that records MCP changes holds the previous definitions, so its manifest is written owner-only.

## Restore safety

A restore checks every destination before writing and refuses zip entries that are absolute or climb out of the Claude folder (zip slip). `pull --exact` never deletes excluded files, files outside the tracked paths, or files that resolve outside the Claude folder, and it deletes only inside roots that both the snapshot and the local config track. Paths are compared after Unicode NFC, case folding and stripping trailing dots and spaces, so a name such as `.Credentials.json` is excluded on every platform. Files behind a symlink that leaves the Claude folder are left untouched. `undo` refuses to run against a different Claude folder than the pull used.

Errors print as one line without a traceback, and no Typer app shows local variables, so a config, token or passphrase cannot leak into terminal output. `CLAUDE_CFG_DEBUG=1` prints a plain traceback without locals. Config, state and backup manifests are created owner-only (0600) from the start, and backup folders are 0700.

## Known limitations users should be aware of

- **The plugin's local history is plain zips in an owner-only folder.** It holds copies of `settings.json` as they are, with any key in it. Auto-save keeps the newest 50 automatic versions, so a secret you later remove from `settings.json` stays in older versions until they are pruned or you delete `~/.claude-cfg/history/`.
- **Without encryption, snapshots are plain zips.** Tracked files (including `settings.json`) are readable by anyone who can read the backend. Turn encryption on, or use a private backend.
- **A Gist is secret, not private.** Gists that `claude-cfg` creates are not public, but anyone with the URL can open one.
- **Credentials are stored in plaintext** in `~/.claude-cfg/config.json`, including the encryption passphrase if you chose to save it. On POSIX systems the file is created with mode 600; on Windows it relies on per-user profile ACLs.
- **The sync state file** `~/.claude-cfg/state.json` records which snapshot you last synced and a hash of each tracked file. It is written owner-only on POSIX.
- **The SFTP backend uses trust-on-first-use** for host keys (`AutoAddPolicy`). The first connection to a host could be MITM'd on a hostile network. Use only with hosts you control on trusted networks.
- **Version 0.2 clients cannot read encrypted snapshots or schema v4.** They refuse v4 snapshots with an upgrade message. Upgrade every machine before pushing from the new version.
