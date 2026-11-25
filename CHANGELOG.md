# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This section will be released as 0.3.0.

### Added
- The `config-history` Claude Code plugin (version 0.3.0). Install it with
  `claude plugin marketplace add razamit/config-history` and
  `claude plugin install config-history@razamit`. It needs no setup: on the
  first session it builds a private Python environment in the plugin's data
  folder, in the background, using the Python already on the machine
  (3.9 or later), and shows one line. Nothing is added to the global Python
  packages. The build downloads the tool's dependencies from PyPI.
- Auto-save. At session start and end, the plugin's hooks save a new version
  when tracked config files changed since the last one, and keep the newest 50
  automatic versions (`config autosave --keep` changes that). Versions saved by
  hand are never deleted. Session start shows one line, for example
  "config-history: saved version 2 (2 files changed: settings.json,
  skills/demo/SKILL.md). To go back, type /config-history:restore". The
  line uses `systemMessage`, so it does not enter Claude's context.
- Zero-setup local history. With no config, the first command writes one that
  stores versions in `~/.claude-cfg/history` (owner-only, not encrypted), with
  the default tracked list, no MCP sync and auto-save on. `init` is optional.
  `init` replaces that config, picks a backend and leaves auto-save off.
- Three plugin skills, and a `config-history` command on the `PATH` of
  Claude's shell while the plugin is enabled. `/config-history:restore`, typed
  with no arguments, is the one command to remember: it lists recent versions
  in plain words, takes a number or a description such as "yesterday", shows
  what would change, offers to restore only some files, and says to restart
  Claude Code and that `/config-history:undo` reverts it. Before a real restore
  it always shows the chosen version and the files that will change, and
  waits for a clear yes in the conversation; Claude Code's permission prompt
  is a second check, not the confirmation. `/config-history:undo`
  reverts the last restore. Both run only when typed. `/config-history:history`
  answers plain questions such as "what changed in my settings?" and can save a
  labelled version; it is the one skill Claude may start by itself, and it
  never restores.
- `claude-cfg pull --only PATH` (and `restore --only`), repeatable, restores
  only a file or a folder of a snapshot. The plan, dry run, backup and `undo`
  cover only those files. It refuses `--exact`, unsafe paths, a value that
  starts with `-` (so `--only --dry-run` cannot turn a dry run into a real
  restore; write `./-name` for such a file) and a path that matches nothing
  (naming the closest matches), never restores MCP servers,
  and leaves the sync state alone, so the next save records the mixed state
  as a new version.
- `claude-cfg history` as an alias of `list`, and `list --limit N`. In local
  wording the list has three columns, Version, When and What changed, shows 10
  versions by default and says how many older ones exist.
- `claude-cfg autosave`, `claude-cfg config autosave [--enable|--disable]
  [--keep N]` and `claude-cfg session-hook start|end`.
- `save` and `restore` as aliases of `push` and `pull`.
- Python 3.9 support. CI now covers Python 3.9 to 3.13.
- `CLAUDE_CFG_HOME` sets the folder for the tool's own files instead of
  `~/.claude-cfg` (absolute paths only). `CLAUDE_CFG_PROGRAM_NAME` sets the
  command name that hints and notices print, so the plugin shows
  `config-history`.
- Snapshot encryption. Snapshots can be encrypted on the client with a
  passphrase (scrypt key derivation, AES-256-GCM, a fresh salt and nonce per
  snapshot). Encrypted objects end in `.zip.enc`. `init` offers it and
  defaults to yes. Existing setups turn it on with `claude-cfg config encrypt`.
  The passphrase comes from `CLAUDE_CFG_PASSPHRASE`, then the saved
  `encryption.passphrase` config value, then a hidden prompt (terminal only).
  Any machine can read both plain and encrypted snapshots, because encryption
  is detected from the file itself. An unencrypted push prints a one-line note.
- `claude-cfg pull --dry-run`, `claude-cfg diff` and `claude-cfg pull --exact`.
  `--exact` deletes tracked local files that the snapshot does not have, asks
  first and takes `--yes` to skip the question. Without a terminal it refuses
  unless `--yes` is given.
- `claude-cfg undo [--force] [--files-only]` reverts the most recent pull that
  has not been undone. It stops if files changed after the pull, unless
  `--force` is given. When the pull changed MCP servers and they cannot be
  put back here, it refuses unless `--files-only` is given, which leaves the
  MCP part pending for a later `undo`.
- `claude-cfg status [--offline] [--all]` shows local changes since the last
  push or pull, whether the backend has a newer snapshot, and a suggested next
  step. The last sync is recorded in `~/.claude-cfg/state.json`.
- `claude-cfg list --keys` and `claude-cfg pull --key` / `diff --key` select a
  snapshot by its exact object key. `--all` lists every file instead of the
  first 20 per group.
- `claude-cfg config track-defaults` adds default tracked entries that an
  older saved list is missing. `push` hints when such entries exist on disk.
- Opt-in sync of user-scope MCP servers: `claude-cfg config mcp --enable`.
  Servers are read from `.claude.json` and restored with
  `claude mcp add-json`, never by editing that file. The `claude` CLI must be
  on `PATH` at restore, version 2.1.327 or later. `init` asks about it.
- Claude Code integration: `claude-cfg integrate install|remove|status` adds
  the session hooks (see Changed) and a `/cfg-push` skill. The notice uses the
  hook's `systemMessage` field, so it does not enter Claude's context.
- `backups.keep` config value (default 10) sets how many pull backups are kept.
- `CLAUDE_CONFIG_DIR` is honored when it is an absolute path.
- Default tracked entries now include `keybindings.json`, `themes/`, `rules/`,
  `output-styles/` and `workflows/`.
- `list` shows whether each snapshot is encrypted.
- Every storage backend implements `delete`, used to clean up after a lost
  push race.
- `pull --allow-plain` and `diff --allow-plain` accept a plain snapshot on a
  machine with encryption on. Without it such a snapshot is refused.
- A passphrase verifier in the config, written by `init` and
  `config encrypt`. Push checks the passphrase against it whatever its source.
  Before a verifier is stored, by setup or by a push on a machine without one,
  the passphrase must open the newest encrypted snapshot on the backend. A
  pull that decrypts a snapshot stores a missing verifier.
- `CLAUDE_CFG_DEBUG=1` shows a traceback (without local values) on errors.
- A pull reports files left untouched because they are symlinks out of the
  Claude folder, and says when the snapshot removed the session hook.

### Changed
- Under `plugins/`, only `installed_plugins.json` and `known_marketplaces.json`
  are captured, restored or deleted. Everything else there (caches, the
  catalog, the blocklist, `store/` and each plugin's `plugins/data/<id>/`
  folder, which holds this plugin's own environment) is excluded.
  `known_marketplaces.json` changes on its own, so a change to it alone no
  longer triggers an automatic save or a notice, and it is left out of the
  file list in those messages. `status` still lists it.
- Plugin updates build the new environment beside the one in use and switch
  only after a successful install, so the old environment keeps saving
  meanwhile. A failed install is retried after 1 hour, doubling up to
  24 hours, and reported at most once a day.
- The plugin installs its dependencies with the exact versions in
  `scripts/plugin-constraints.txt`, maintained with each release, and
  `plugin.json` declares the package index hosts under `network.hosts`.
  `typer[all]` became `typer`, since the `all` extra no longer exists.
- `/config-history:restore` pre-approves only `history`, `diff` and the dry
  run with `--dry-run` first (`restore --dry-run --point *`), and
  `/config-history:undo` pre-approves nothing, so a real restore or undo goes
  through Claude Code's permission prompt. `/config-history:history`
  pre-approves only its five commands exactly as written, with no wildcard,
  so `--limit`, `--point` or a save label asks for permission first. Its
  description is scoped to Claude Code's own config in `~/.claude`. It
  passes a save label after `--`, so a label starting with `-` works.
- Under the `config-history` name, a hint names a slash command the user can
  type (`/config-history:restore`, `/config-history:undo`,
  `/config-history:history`) when one does the job, instead of a shell command
  that only Claude's shell has. A command no slash command covers is worded as
  something to ask Claude, such as "Ask Claude to turn it on (it runs
  `config-history config autosave --enable`)". A command that asks a question
  at a terminal (`config encrypt`, a save that prompts for the passphrase,
  `config mcp --enable`) names `claude-cfg ...` "in a terminal", since Claude's
  shell cannot answer the prompt. `status` suggests asking Claude to save a
  version. Under `claude-cfg` the hints are unchanged.
- The "not encrypted" notice after a save no longer shows for the automatic
  local history, which stays on this machine. It still shows for a backend set
  up with `init`.
- A partial restore that changed nothing no longer says that the next save
  records the mix as a new version.
- Times are shown in the machine's time zone with a relative phrase, such as
  "2 hours ago (today 18:11)", "yesterday 09:30" or "3 days ago (Sun 22 Nov
  14:05)", in `list`, `status`, `diff`, restore and undo output. They are
  still stored in UTC. A time whose local value falls outside the calendar
  (year 1 or 9999) is shown in UTC instead of failing the command.
- The GitHub repository was renamed from `claude-cfg` to `razamit/config-history`.
  The PyPI package and the command keep the name `claude-cfg`.
- With the local history or under the `config-history` name, messages say
  `save` and `restore` and "version N" instead of `push`, `pull` and
  "snapshot #N", and `status` says "Last saved: version N" without a remote
  line. The sign-in reminder after a restore shows only for a snapshot taken
  on another machine.
- Session start budgets now nest inside the 15 second hook timeout: the
  remote check gets 3 seconds and the auto-save 6.
- `claude-cfg integrate install` now adds a SessionStart hook
  (`claude-cfg session-hook start`) and a SessionEnd hook
  (`claude-cfg session-hook end`), and replaces the older
  `claude-cfg status --hook` entry. The hooks auto-save when auto-save is on
  and still print a notice when the backend has a newer snapshot. Do not use
  `integrate` and the plugin together, since each installs session hooks.
- Auto-save is on for the automatic local history and off for a backend chosen
  with `init`. With a backend, auto-save waits while the backend has a snapshot
  newer than this machine's last sync.
- Snapshot `schema_version` bumped to **4** (adds the tracked list and file
  hashes). Version 0.2 clients refuse v4 snapshots and cannot read encrypted
  ones, so upgrade every machine before the first push from the new version.
- Snapshot object keys end in a random 6-character hex suffix, such as
  `001_20260507T101530_initial-setup_a3f9c1.zip`. Keys without a suffix still
  read fine.
- The objects under `snapshots/` are now the source of truth for which
  snapshots exist. `index.json` is only a cache of each snapshot's message and
  machine, and is rebuilt when it is missing or stale.
- A pull backs up only the files it overwrites or deletes, under
  `~/.claude-cfg/backups/<UTC time>/files/` with a `backup-manifest.json`. It
  writes no backup when nothing changes, and keeps the newest `backups.keep`
  backups. Backups made by 0.2 count toward that limit but cannot be undone.
- `cryptography` is now a runtime dependency.
- The restore path is split into small modules (plan, writer, backup manager,
  undo manager, snapshot store). The `claude_cfg.cli` module is now a package.
- `config show` and `config set` also mask `passphrase` values.

### Fixed
- The plugin's install lock went stale after 15 minutes while the install
  steps may take 22, so a second install could start mid-build. It now goes
  stale after 30 minutes.
- On Windows, the `plugin-python` pointer file was written with CRLF and the
  wrapper kept the CR, so `config-history` never found its environment.
- A relative `CLAUDE_CFG_HOME` was honored by the plugin scripts but ignored
  by the tool. The scripts now ignore it too.
- The "needs Python" notice repeated every session. It now shows at most
  once a day.
- The macOS `/usr/bin/python3` stub check missed a path spelled
  `/usr/bin//python3`, which some shells report for a `PATH` entry ending in
  `/`.
- `pull` was overlay-only, with no way to remove files that had been deleted
  on another machine. `pull --exact` now does that.
- The pre-pull backup copied whole tracked folders, including caches and
  `.git` folders. It now copies only the files the pull changes.
- Two machines pushing at the same time could drop a snapshot. Pushes now
  check for a colliding id after uploading; a pusher that sees any other
  object with its id deletes its own and retries under a freshly listed id
  after a short random wait, up to 5 times.
- The Gist backend raises a clear error when GitHub truncates the gist's file
  list at 300 files, instead of working from a partial list. A push to a full
  gist, or of a snapshot over the 10 MB the Gist API can serve back, is
  refused before upload, and deleting works on a full gist.
- A push that loses an id race and then cannot delete its own object retries,
  and then names the leftover object instead of raising a raw backend error.
- A file on this machine where the snapshot has a folder (or the reverse) now
  stops the pull before anything is written.
- `init` never saved the id of a newly created Gist, because it read the id
  before the first upload. It now saves the id after the first push.

### Security
- Removed a source comment that called the exclusion list "safe for public
  backends". Only `.credentials.json` is excluded, and files such as
  `settings.json` can still hold API keys. The docs now say so and recommend
  encryption.
- Added client-side encryption of snapshots (see Added), so a backend only
  holds ciphertext for the snapshot contents. Snapshot ids, timestamps, the
  message slug in object names and the `index.json` cache stay readable.
- Pull backups that record MCP server definitions are written owner-only,
  because definitions often hold tokens. Enabling MCP sync without encryption
  needs an explicit confirmation.
- Restore checks every destination before writing, so a snapshot cannot write
  outside the Claude folder. `pull --exact` never deletes excluded files,
  files outside the tracked paths, or files that resolve outside the folder.
- The exclusion list compares paths after Unicode NFC, case folding and
  stripping trailing dots and spaces, so a case variant such as
  `.Credentials.json` cannot slip past it. Snapshot files are matched to
  files on disk by exact name first, and by case only when the Claude folder
  is on a case-insensitive filesystem, so a case variant is not a "local
  extra" on macOS and Windows and is its own file on Linux. Exact deletes only happen in roots both the snapshot and the local
  config track.
- The encryption envelope (magic `CCFGENC2`) stores the scrypt parameters in
  its authenticated header, accepts only N 2^14 to 2^18 with r=8 and p=1, and the manifest id must match the
  object key. A machine with encryption on refuses plain snapshots.
- MCP restore checks for `claude` 2.1.327 or later and a normal terminal
  (outside Claude Code) before changing anything, validates server names,
  and puts a replaced server back when its new definition fails to add.
- `undo` refuses a pull made into another `CLAUDE_CONFIG_DIR` and no longer
  rewinds the sync state past a later push or pull. Backups keep file modes
  and their folders are 0700; config and state files are created 0600.
- Errors no longer print tracebacks with local variables.
- Snapshot messages and machine names from the backend are shown without
  control, format (such as bidi overrides) or separator characters, and with
  rich markup escaped, in the hook notice, `list`, `status`, `diff`, `pull`
  and `init`. The hook notice caps the machine name at 40 characters. `.claude.json` and its backups are never captured.

## [0.2.0] - 2026-06-09

### Added
- Interpreter normalization: a leading `python`/`python3` launcher in a tracked
  config command is stored as a neutral `${PYTHON}` token and resolved on restore
  to whichever launcher (`python3` preferred, then `python`) exists on the target
  machine. Fixes status-line / hook commands breaking when a snapshot spelled
  `python` is restored on a host that only has `python3` (e.g. macOS).
- `init` now detects existing snapshots on a configured backend and prompts to
  either push this machine or restore an existing snapshot, instead of always
  pushing.
- `pull` reports the backup directory and, on a cross-platform restore, the
  resolved python launcher.

### Changed
- Snapshot `schema_version` bumped to **3** (new snapshots embed the `${PYTHON}`
  token, which older readers would not expand). Restoring a v3 snapshot with an
  older `claude-cfg` is refused with a clear upgrade message.

## [0.1.0] - 2026-05-07

### Added
- Initial release of `claude-cfg`.
- `init`, `push`, `pull`, `list`, `config show`, `config set` commands.
- `--version` / `-V` flag.
- Storage backends: local folder, AWS S3, Cloudflare R2, GitHub Gist, SFTP.
- Versioned snapshots with monotonic IDs, ISO-8601 timestamps, and messages.
- Manifest-per-snapshot recording machine, platform, and file list.
- Auto-discovery of `~/.claude/<path>` references inside tracked files (e.g. status-line scripts).
- Safe-pull behaviour: current config is backed up to `~/.claude-cfg/backups/<ts>/` before restore.
- Credential masking in `config show` and `config set`.
- Config file `chmod 0600` on POSIX after writing.
- Cross-platform CI on Linux / macOS / Windows × Python 3.10 / 3.11 / 3.12 / 3.13.

### Security
- `extract_zip` rejects archive entries that escape the destination directory (zip slip).
- `_expand_referenced_files` rejects `~/.claude/<path>` references that resolve outside `~/.claude/`.

[Unreleased]: https://github.com/razamit/config-history/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/razamit/config-history/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/razamit/config-history/releases/tag/v0.1.0
