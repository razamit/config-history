---
name: save
description: Save a version of your Claude Code config now, with an optional message.
argument-hint: "[message]"
disable-model-invocation: true
allowed-tools:
  - Bash(config-history save)
  - Bash(config-history save *)
---

Save a version of the user's Claude Code config with config-history.

The user's message, which may be empty: $ARGUMENTS

- If the message is empty, run `config-history save` with no arguments.
- Otherwise run `config-history save -- '<message>'`, with the message as one single-quoted shell argument after `--`, so a message that starts with `-` is not read as an option. Write each single quote inside the message as `'\''`. Do not add or change any other part of the message.

Run nothing else. Report the command's output as it is, without adding commentary. If the command fails, show its output and stop.
