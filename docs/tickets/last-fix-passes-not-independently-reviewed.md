# The last fix pass on the tool and the fix pass on the plugin were not independently reviewed

Status: OPEN · Priority: MEDIUM · Type: review gap · Cost: none

## Symptom

Two rounds of fixes were checked by the test suite and by end-to-end runs, but
not by a reviewer reading the code with fresh eyes. Both earlier reviews found
problems that the tests of the time did not, including problems introduced by
fixes.

## Evidence

Sequence on 2026-11-25:

1. First build of the tool: independent review found 8 significant problems.
2. First fix pass (21 items): the same reviewer verified it and found 2 new
   problems the fixes introduced (case folding applied on every filesystem;
   `undo` stranding MCP servers), plus 7 smaller ones.
3. Second fix pass (items A to I, `301 passed` to `353 passed`): **no review**.
   It changed path matching, the encryption envelope and its bounds, the
   passphrase check against the backend, the Gist limits and display text
   cleaning.
4. Plugin and auto-save build: independent review found 5 significant problems.
5. Plugin fix pass (12 items, `470 passed` to `523 passed`): **no review**. It
   changed the `plugins/` allowlist and volatile paths, the installer (build
   beside and swap, back-off), skill permissions, time budgets and the local
   wording.

Both unreviewed passes were followed by a full suite run on Python 3.12 and
3.9.6 and by an end-to-end run in a throwaway home; the plugin pass also by
three headless real sessions.

## Why it matters

Step 2 is direct evidence that a fix pass on this code can add defects that its
own tests pass. The areas touched in steps 3 and 5 include deletion rules,
encryption parameters and an installer that removes old environments.

## Scope to decide

- Run one more independent review limited to the diff of those two passes
  before publishing.
- OR publish from the own marketplace first and review before any directory
  submission.

No code change made by this ticket. It is an observation on the record.
