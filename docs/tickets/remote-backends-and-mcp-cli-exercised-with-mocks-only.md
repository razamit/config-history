# S3, R2, SFTP, Gist and the real `claude mcp` command were exercised with mocks only

Status: OPEN · Priority: MEDIUM · Type: verification gap · Cost: none

## Symptom

Every end-to-end run on 2026-11-25 used the local folder backend with MCP sync
off. The code paths for the remote backends and for restoring MCP servers ran
only against fakes.

## Evidence

- Stage 1 report: "The S3, Gist and SFTP `delete` methods are tested with mocks
  only." The Gist `delete` (set the file to null) was later confirmed against
  the GitHub REST docs by the reviewer, but not run against GitHub.
- New in this work and never run for real: `delete` on each provider, the
  lost-race re-key, which uploads, lists and deletes
  (`claude_cfg/snapshot_store.py`), and the Gist limits (300 files, 10 MB per
  file, `claude_cfg/providers/gist.py`).
- MCP restore runs `claude mcp remove` and `claude mcp add-json <name> - --scope
  user` through an injected runner. `tests/conftest.py` has an autouse fixture
  that blocks the real binary. Stage 3 report: "Not checked: behaviour against
  the real `claude mcp` CLI, and whether it echoes definitions on stderr."
- The version floor (2.1.327 for stdin input) and the rule that `add-json` must
  run outside a Claude Code session come from the docs, not from a run.

## Why it matters

The push race fix deletes objects on the backend. A provider whose `delete`
misbehaves could leave duplicates or, worse, remove the wrong object. MCP
definitions hold tokens, so a surprise in how the CLI handles stdin or errors
matters more than usual. The local backend, which the plugin uses by default,
is not affected.

## Scope to decide

- Run push, a forced race, list, pull and delete against one real bucket and
  one real Gist with throwaway credentials.
- Run an MCP round trip (capture, restore on a second profile, undo) with the
  real CLI from a normal terminal, using a dummy server definition.
- OR mark the remote backends and MCP sync as experimental in the README until
  that is done.

No code change made by this ticket. It is an observation on the record.
