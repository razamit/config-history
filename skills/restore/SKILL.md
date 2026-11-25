---
name: restore
description: Restore your Claude Code config to a saved version, after showing the plan and asking you to confirm.
argument-hint: "<version-number> [exact]"
disable-model-invocation: true
allowed-tools:
  - Bash(config-history list)
  - Bash(config-history restore --point * --dry-run)
---

Restore the user's Claude Code config to a saved version with config-history.

The user's arguments: $ARGUMENTS

Follow these steps in order.

1. Find the version number in the arguments. If there is none, run `config-history list`, show its output, ask the user which version number to restore, and stop. Never choose a version number yourself, and never use one the user did not give. In the steps below, N is the user's number, digits only.
2. Decide on exact mode. Use it only if the user asked to also remove files that are not in that version (for example by writing "exact"). Otherwise do not use it.
3. Show the plan:
   - Normal mode: run `config-history restore --point N --dry-run`.
   - Exact mode: run `config-history restore --point N --exact --dry-run`, and point out the list of files it would delete.
   Show the output as it is.
4. Ask the user to confirm the restore. Stop and wait for the answer. Continue only on a clear yes. In exact mode, the user must confirm the delete list too.
5. Restore:
   - Normal mode: run `config-history restore --point N --yes`.
   - Exact mode: run `config-history restore --point N --exact --yes`.
   Only the dry run in step 3 is pre-approved. Claude Code asks the user for permission before this command runs, as a second confirmation; if the user declines, stop.
6. Show the output as it is, without adding commentary. Then tell the user to restart Claude Code so the restored settings load, and that `config-history undo` reverts this restore.

If any command fails, show its output and stop. Run no other commands.
