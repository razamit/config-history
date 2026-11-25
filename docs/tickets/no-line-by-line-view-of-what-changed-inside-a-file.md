# `diff` names the files that changed but never shows what changed inside them

Status: OPEN · Priority: MEDIUM · Type: deferred feature, privacy question · Cost: none

> Deferred on purpose during the easy-flow work of 2026-11-25 (open question 4
> in `docs/DECISIONS.md`). Not a defect in what was built: the file-level list
> is correct. Related to decision row 7, which keeps session notices out of
> Claude's context for the same reason.

## Symptom

A user who asks "what changed in my settings?" gets the name of the file and
nothing about its contents. To learn that the model went from `opus` to
`sonnet` they have to restore the old version or open the zip by hand.

## Evidence

Throwaway home, 2026-11-25, after saving `{"model":"opus"}` and then changing
`settings.json` to hold a different model and an `env` block with a key:

```
$ config-history diff
Version 1, saved just now (today 19:34): saved by you
Create (0)
Overwrite (1)
  ~ settings.json
Delete (0)
Unchanged: 1 file(s)
```

The history list is at the same level ("What changed" holds file names or the
label).

## Why it matters

"What changed" is the first question after something breaks, and the answer
decides which version to go back to. Without it the guided restore asks the
user to choose between versions described only by time and file names.

It was not built because `settings.json` and MCP definitions can hold API keys
and tokens. Inside the plugin every command's output lands in Claude's context
and in the session transcript, so a line diff of `settings.json` would copy
secrets there. The `history` skill is the one skill Claude may start by itself,
and `diff` is one of its pre-approved commands, so this would happen without a
permission prompt.

## Scope to decide

- A key-level summary for JSON files: which keys were added, removed or
  changed, with no values ("settings.json: model changed, env.API_KEY added").
- OR a line diff with values masked for keys that look like secrets (a pattern
  list misses unknown names, the same weakness decision row 3 rejected for
  redaction on push).
- OR a line diff only in the plain `claude-cfg` CLI in a terminal, never under
  the plugin name.
- OR leave it at file level.

No code change made by this ticket. It is an observation on the record.
