# Under the plugin name a few messages still tell the user to run a command they cannot type

Status: OPEN · Priority: LOW · Type: wording gap · Cost: none

> What is left of finding D of the easy-flow review on 2026-11-25. The common
> hints were fixed (decision row 17). These are the ones left as they were,
> plus one limit of the fix itself.

## Symptom

The `config-history` command exists only on the `PATH` of Claude's shell. A
user cannot type it in their own terminal. Four messages still name it as
something to run, and the hints that name `claude-cfg ... in a terminal` assume
the user installed the CLI.

## Evidence

Left with the shell form under the plugin name:

```
claude_cfg/snapshot_selection.py:54   No snapshot with key ... Run `config-history list` to see the keys.
claude_cfg/snapshot_store.py:207      Use `config-history pull --key <key>` to select one ...
claude_cfg/config.py:154              Config not found at ... Run `config-history init` first.
claude_cfg/cli/init_command.py        (the `init` wizard, CLI only)
claude_cfg/cli/integrate_commands.py  (the `integrate` commands, CLI only)
```

The first two apply only to a shared sync backend, the third only when the
config file is missing and the automatic default could not be written.

Still in the slash form that decision row 17 calls awkward for `status`:

```
claude_cfg/session_hook_lines.py:79   ... Save them with: /config-history:history save
```

It works (the `history` skill takes "save" as its argument). It is shown only
for a backend set up with `init`, where auto-save is off.

Limit of the fix: `claude_cfg/cli/mcp_prompts.py:34` prints "MCP server sync is
off. Turn it on with `claude-cfg config mcp --enable` in a terminal." A user
who installed only the plugin has no `claude-cfg` command. The other
"in a terminal" hints appear only after encryption, a backend or MCP sync was
set up, which already needed the CLI. `README.md:87` explains how to get it.

## Why it matters

Small. Each message is reached only on a path a plugin-only user with the
default local history is unlikely to take. It matters for the claim in
`CHANGELOG.md` that hints under the plugin name are things the user can act on.

## Scope to decide

- Word the four shell-form messages with the same three tiers as the rest.
- Add "(install it with `pip install claude-cfg`)" to the terminal hints under
  the plugin name, or only to the MCP one.
- Reword the session-start line to "ask Claude to save a version now", as
  `status` does.
- OR leave them: all sit on sync-backend paths.

No code change made by this ticket. It is an observation on the record.
