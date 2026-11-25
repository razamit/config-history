---
name: history
description: Saved versions of the user's Claude Code config in ~/.claude (settings, hooks, skills, agents, commands, MCP servers, CLAUDE.md). Use when they ask what changed in it, when Claude Code misbehaves after a change to it, or to see or save versions.
argument-hint: "[a question, or save and a label]"
allowed-tools:
  - Bash(config-history history)
  - Bash(config-history list)
  - Bash(config-history diff)
  - Bash(config-history status)
  - Bash(config-history save)
---

Answer the user's question about the history of their Claude Code config with config-history. config-history saves a version automatically when a session starts or ends and something changed.

The user's request, which may be empty: $ARGUMENTS

Use only these commands:

- `config-history history` lists the recent versions, newest first: number, when, and what changed. `config-history history --limit N` shows more. `config-history list` is the same command.
- `config-history diff` compares the current config with the last saved version. `config-history diff --point N` compares it with version N, where N is digits only. Both write nothing.
- `config-history status` says when the config was last saved and what changed since.
- `config-history save` saves the current state as a new version. When the user gave a label, run `config-history save -- '<label>'` instead: the label is one single-quoted argument after `--`, with each single quote inside it written as `'\''`.

Only the five commands exactly as written, with nothing after them (`config-history history`, `config-history list`, `config-history diff`, `config-history status` and `config-history save`), run without asking. Anything with more after it, such as `--limit`, `--point` or a save label, makes Claude Code ask the user for permission first. That is expected; do not try to avoid it.

Answer in plain words. Name the version numbers, when they were saved and the files involved, and leave out details the user did not ask about. With no request, show the recent versions as a short list.

Save only when the user asks to save or label the current state.

If the user wants to go back to an earlier version, do not restore anything from here. Show the versions that could match and tell them to type `/config-history:restore`, which walks them through it and can restore only some files.

If a command fails, show its output and stop.
