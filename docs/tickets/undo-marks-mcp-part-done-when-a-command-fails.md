# `undo` marks its MCP part done even when an MCP command ran and failed

Status: OPEN · Priority: LOW · Type: defect, known limitation · Cost: none

> Narrower than the case fixed on 2026-11-25: when the MCP preflight fails,
> `undo` now refuses up front unless `--files-only` is passed, and keeps the MCP
> part pending. This ticket is about a command that passes the preflight and
> then fails.

## Symptom

During `undo`, if the preflight passes (the `claude` CLI is present, new enough,
and not inside a session) but a `claude mcp remove` or `add-json` command then
fails, the files are reverted, the failure is reported, and the backup's MCP
part is still marked done. A second `undo` does not retry it.

## Evidence

Final fix-pass report, 2026-11-25, under "Not verified": "MCP commands that run
and fail during undo still mark the MCP part done, as before."

The handling is in `claude_cfg/undo_manager.py` and
`claude_cfg/mcp_server_sync.py`. The previous definitions stay in the backup's
`backup-manifest.json` (owner-only) until that backup is pruned.

## Why it matters

Only users who turned on MCP sync are affected, and only when a command fails
mid-undo. The definitions are not lost at once, but the only way back is to
read them out of the backup manifest by hand before pruning removes it.

## Scope to decide

- Keep the MCP part pending when any command fails, so the next `undo`
  retries the servers that were not put back, and keep such a backup out of
  pruning (the pending mechanism already exists for the preflight case).
- OR leave it and document where the definitions can be found.

No code change made by this ticket. It is an observation on the record.
