---
name: diff
description: Show what changed in your Claude Code config since the last saved version, or since a version you name.
argument-hint: "[version-number]"
disable-model-invocation: true
allowed-tools:
  - Bash(config-history diff)
  - Bash(config-history diff *)
---

Show what changed in the user's Claude Code config with config-history.

The user's arguments, which may be empty: $ARGUMENTS

- If the arguments are empty, run `config-history diff`.
- If they contain a version number, run `config-history diff --point N`, where N is that number exactly as the user gave it. Use only digits; if the arguments hold anything that is not a version number, ask the user which version they mean instead of guessing.

Run nothing else. Show the output as it is, without adding commentary. If the command fails, show its output and stop.
