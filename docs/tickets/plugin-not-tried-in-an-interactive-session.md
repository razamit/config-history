# The config-history plugin has only run in headless sessions, never in an interactive one

Status: OPEN · Priority: HIGH · Type: verification gap · Cost: none

> Blocks publishing with confidence (decision row 12). Differs from
> `plugin-launcher-untested-on-windows-and-linux.md`, which is about other
> operating systems; this one is about the interactive terminal on macOS.

## Symptom

Every real-session check on 2026-11-25 used `claude -p` (headless) with
`--plugin-dir`. Nobody has seen the plugin in the interactive terminal, and
three behaviors were never exercised against a real session at all.

## Evidence

Headless runs, Claude Code 2.1.332, plugin loaded for the session only:

```
plugins: ['config-history', ...]
skills/commands with our prefix: ['config-history:diff', 'config-history:history',
  'config-history:restore', 'config-history:save', 'config-history:status',
  'config-history:undo']
hook/notice text: config-history is setting up for first use (about a minute). ...
hook/notice text: config-history: saved version 1, the first version of your settings.
tool_use: Bash {'command': 'config-history status'}
tool_result: Last saved: version 1 (2026-11-25 16:14:34), saved 2026-11-25 16:14:34
             Local changes: none.
             Nothing to do.
```

The model answered `NONE` when asked whether a line starting with
"config-history" was in its context, in both runs that printed a notice.

Not exercised in any real session:

- How the `systemMessage` notice looks on screen.
- `/config-history:restore`, which must stop at Claude Code's permission prompt
  before the real restore, and `/config-history:undo`.
- A save at session end when something changed during the session. The end
  hook hands off to a detached process because plugin SessionEnd hooks are
  limited to 1.5 seconds; whether that process survives the session exiting was
  only checked with the hook run by hand.

## Why it matters

These are the moments a new user sees first. The restore path changes files, so
its confirmation has to be seen working, not inferred from the skill's
`allowed-tools` line.

## Scope to decide

- Start a session with `claude --plugin-dir <repo>`, change a setting, exit,
  start again, then run `/config-history:history`, `:diff`, `:restore` and
  `:undo`, and record what was shown.
- OR install from the marketplace on a second machine after the first push and
  do the same there.

No code change made by this ticket. It is an observation on the record.
