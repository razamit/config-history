---
name: undo
description: Undo the last config-history restore.
disable-model-invocation: true
---

Run `config-history undo` and nothing else. It changes files in the user's Claude Code config, so it is not pre-approved: Claude Code asks the user for permission before it runs. If the user declines, stop.

Show the output to the user as it is, without adding commentary. If it succeeded, tell the user to restart Claude Code so the settings load. If the command fails, show its output and stop.
