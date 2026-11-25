# The config-history plugin has only run in headless sessions, never in an interactive one

Status: OPEN · Priority: HIGH · Type: verification gap · Cost: none

> Update 2026-11-25, easy-flow work (decision row 15): the plugin now has
> three skills, not the six listed under Evidence, and two more behaviors are
> unverified in any real session, headless or interactive. First, the guided
> `/config-history:restore` flow: picking a version from words such as
> "yesterday", offering only some files, and above all the confirmation in the
> conversation before the real restore, which exists only as skill text and a
> test on that text. Second, whether Claude starts the `history` skill by
> itself from a plain question such as "what changed in my settings?". Both
> belong in the session described under Scope to decide. See also
> `command-substitution-under-wildcard-allow-rules-not-tested-live.md`.

> Update 2026-11-25, later the same day: the second of those was checked in
> three headless sessions the owner approved (Claude Code 2.1.332, Haiku,
> `--plugin-dir`, default permission mode, tool data in a scratch
> `CLAUDE_CFG_HOME`, deleted afterwards). The plugin registered three skills
> (`config-history:history`, `:restore`, `:undo`). Asked "what changed in my
> settings?" with no command, Claude's first tool call was
> `Skill {"skill": "config-history:history", "args": "what changed in my
> settings"}`, so the pickup works. Claude Code then refused it with "Execute
> skill: config-history:history. The user can add the allow rule
> Skill(config-history:history)": a skill Claude starts by itself needs the
> user's approval once, which a headless session cannot give. In an
> interactive session that is one prompt; how it looks is still unseen. Typed
> as `/config-history:history what changed in my settings?`, the skill ran
> `config-history history` and `config-history status` with no permission
> denial and answered from the one saved version, so the five exact
> pre-approved commands match in practice. Still unverified in any real
> session: the guided restore flow and its confirmation in the conversation,
> `/config-history:undo`, the on-screen notice, and the save at session end.

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
