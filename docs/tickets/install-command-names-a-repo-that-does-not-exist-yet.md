# The README's install command points at `razamit/config-history`, and that repository does not exist yet

Status: OPEN · Priority: HIGH · Type: publishing blocker, owner action · Cost: none

> Update 2026-11-25, later the same day: the repository is renamed. The owner
> asked Claude to run `gh repo rename config-history -R razamit/claude-cfg`
> after the rename in GitHub's settings did not take effect twice.
> `gh repo view razamit/config-history` now returns
> `{"nameWithOwner":"razamit/config-history", ... "visibility":"PUBLIC"}`, this
> clone's `origin` is `https://github.com/razamit/config-history.git`, the old
> name redirects (`git ls-remote` on it returns the same head, `700ed85`), and
> the CI badge URL answers 200. Steps 1 and 2 of the Fix are done. Step 3 is
> not: `.claude-plugin/marketplace.json` exists on `feat/hardening-and-coverage`
> and returns 404 on `main`, so `claude plugin marketplace add
> razamit/config-history` cannot work until the branch is merged. The ticket
> stays open for that one check, which was not run.

> Follows from decision row 16 (the owner chose to rename the repository).
> Blocks publishing (decision row 12). The rename on GitHub is the owner's to
> do.

## Symptom

Every URL outside `docs/` was moved to `razamit/config-history` on 2026-11-25.
The repository on GitHub is still `razamit/claude-cfg`, and so is this clone's
`origin`. Until the rename, the install command in the README fails, and so do
the CI badge, the clone URL and the compare links in `CHANGELOG.md`.
`CHANGELOG.md` also states under `## [Unreleased]` that the repository "was
renamed", which is not true yet.

## Evidence

```
$ gh repo view razamit/config-history --json name,url
GraphQL: Could not resolve to a Repository with the name 'razamit/config-history'. (repository)
$ gh repo view razamit/claude-cfg --json name,url
{"name":"claude-cfg","url":"https://github.com/razamit/claude-cfg"}
$ git remote -v
origin	https://github.com/razamit/claude-cfg.git (fetch)
origin	https://github.com/razamit/claude-cfg.git (push)
$ grep -n "marketplace add" README.md
26:claude plugin marketplace add razamit/config-history
$ git grep -n "razamit/claude-cfg" -- . ':!docs'
(no output)
```

## Why it matters

The first thing a new user does is paste the install command. Pushing still
works after a rename, because GitHub redirects the old name, but a redirect
breaks if another repository later takes the old name.

## Fix

1. The owner renames the repository on GitHub to `config-history`, before the
   branch is merged to `main` or right after.
2. Then, in this clone:
   `git remote set-url origin https://github.com/razamit/config-history.git`
3. Check `claude plugin marketplace add razamit/config-history` from a clean
   machine or a throwaway `HOME`, and close this ticket.

No code change made by this ticket. It is an observation on the record.
