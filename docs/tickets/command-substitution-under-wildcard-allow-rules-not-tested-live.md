# Nobody has tested whether a `$(...)` inside a pre-approved wildcard command makes Claude Code ask for permission

Status: CLOSED (2026-11-25) · Priority: MEDIUM · Type: verification gap, security · Cost: two headless Haiku sessions

> Closed 2026-11-25, the day it was filed, by a live test the owner approved:
> on Claude Code 2.1.332 in default permission mode, command substitution,
> backticks and chaining under a wildcard allow rule are all refused without
> approval. Result below under "Live test". Progress entry of 2026-11-25
> (easy flow).

> Spawned by finding A of the easy-flow review on 2026-11-25 (decision row 15).
> Part of the wider gap in `plugin-not-tried-in-an-interactive-session.md`, but
> narrower: this is one yes or no question with a security consequence.

## Symptom

The `history` skill now pre-approves five exact commands and no wildcard, so
this question no longer applies to it. The `restore` skill still pre-approves
three wildcard rules. Whether Claude Code prompts when the wildcard part holds a
command substitution is not known.

## Evidence

`skills/restore/SKILL.md`, frontmatter:

```
allowed-tools:
  - Bash(config-history history)
  - Bash(config-history history *)
  - Bash(config-history diff)
  - Bash(config-history diff *)
  - Bash(config-history restore --dry-run --point *)
```

The reviewer (Fable 5.2) read the permissions documentation on 2026-11-25 and
reported that it settles chaining (`allowed-cmd && other` still prompts) and
redirection, and says nothing about `$(...)` or backticks under an allow rule.
That reading was not repeated in the session that filed this ticket. No live
test was run, because a real session needs the owner's real `~/.claude`.

A command such as `config-history diff --point "$(some other command)"` would
run the inner command first. If no prompt appears, the wildcard rules let any
command run while the restore skill is active.

## Live test

A throwaway plugin with one skill whose only rule was `Bash(echo probe *)`,
run twice with `claude -p "/permprobe:probe" --plugin-dir <scratch> --model
haiku --permission-mode default --no-session-persistence`. In headless mode a
command that needs approval is refused, so a refusal here is a prompt in an
interactive session. `/usr/bin/cksum /dev/null` was the inner command because
nothing in the owner's settings allows it (the control shows that).

```
echo probe plain                              -> ok: probe plain
/usr/bin/cksum /dev/null                      -> ERROR This command requires approval
echo probe "$(/usr/bin/cksum /dev/null)"      -> ERROR Quoted text in this command can't be checked before it runs
echo probe $(/usr/bin/cksum /dev/null)        -> ERROR A nested command in this command can't be checked before it runs
echo probe `/usr/bin/cksum /dev/null`         -> ERROR A nested command in this command can't be checked before it runs
echo probe --point 3; /usr/bin/cksum /dev/null -> ERROR This Bash command contains multiple operations. The following part requires approval: /usr/bin/cksum /dev/null
```

Limits of the test: one Claude Code version (2.1.332), default mode only, and
the behavior is not in the documentation, so it can change. It says nothing
about bypass or auto mode, where no command prompts anyway.

## Why it matters

Less than it would for the `history` skill: `restore` runs only when the user
types it (`disable-model-invocation: true`), and the text Claude reads during
the flow (labels and file names in the history list) is written by the user or
by auto-save on the default local history. On a shared sync backend another
machine writes those labels. The three wildcard rules are needed for the flow
to preview a chosen version without a prompt on every step.

## Scope to decide

- Run one live check in a real session: a skill that pre-approves
  `Bash(echo *)`, then ask Claude to run `echo "$(date)"`, and record whether
  the permission prompt appears. If it prompts, close this ticket and consider
  widening the `history` skill again. [Done 2026-11-25, see Live test. The
  restore skill's wildcard rules stay. Whether to widen the `history` skill is
  left with the owner.]
- OR narrow the restore skill without testing: exact rules for `history`,
  `history --limit 30` and `diff`, and accept a prompt on every
  `diff --point N` and every dry run. [Not needed.]

No code change made by this ticket. It is an observation on the record.
