---
name: restore
description: Go back to an earlier version of your Claude Code config. Pick a version by number or in your own words, see what would change, then restore all of it or only some files.
argument-hint: "[version number or a description, optional]"
disable-model-invocation: true
allowed-tools:
  - Bash(config-history history)
  - Bash(config-history history *)
  - Bash(config-history diff)
  - Bash(config-history diff *)
  - Bash(config-history restore --dry-run --point *)
---

Help the user put their Claude Code config back to an earlier saved version with config-history. Speak in plain words and keep each message short.

What the user asked for, which may be empty: $ARGUMENTS

Follow these steps in order. In the commands below, N is a version number, digits only. Always put `--dry-run` first, right after `restore`, when you preview.

1. Run `config-history history` and read the recent versions. Each row has a version number, when it was saved, and what changed. Run `config-history history --limit 30` if you need older ones.
2. Choose the version:
   - If the user gave a number, use it.
   - If they described it in words, such as "yesterday" or "before the model change", pick the version that matches. Run `config-history diff --point N` if you need to see what a version holds. If more than one version could match, ask instead of guessing.
   - If they gave nothing, show the three to five most recent versions as a short plain list (number, when, what changed) and ask which one they want. Stop and wait for the answer.
3. Run `config-history restore --dry-run --point N` to see which files would be created or overwritten. If nothing would change, say so and stop.
4. If more than one file would change, ask whether to restore everything or only some of the files, and wait for the answer. For only some, add one `--only <path>` per file or folder they chose, such as `config-history restore --dry-run --point N --only settings.json --only skills/demo/`, to show the smaller plan.
5. Confirm with the user in the conversation. This step is required every time, even when the user named the version:
   - Show the chosen version: its number, when it was saved, and its label or what changed.
   - Show the list of files that will change, from the last dry run.
   - Ask: "Restore this version now?" Then stop and wait for the answer.
   - Go on only after a clear yes. A vague answer, another question, or no answer means no restore: say that nothing was changed and stop.
   - Claude Code's permission prompt for the restore is a second check, never a replacement for this confirmation. Ask here even when that prompt is turned off or was already approved.
6. Restore with the same version and the same `--only` options as the last dry run:
   - Everything: `config-history restore --point N`
   - Only some files: `config-history restore --point N --only <path>`
   Never add `--exact` unless the user asked to also remove files that are not in that version. In that case, first run `config-history restore --dry-run --point N --exact`, show the list of files it would delete, ask the user to confirm that list and wait for a clear yes, and only then run `config-history restore --point N --exact --yes`. `--exact` cannot be combined with `--only`.
   If the user declines the permission prompt, stop.
7. Tell the user what was restored, that they need to restart Claude Code so the restored settings load, and that `/config-history:undo` reverts this restore.

If a command fails, show its output and stop. Run no other commands.
