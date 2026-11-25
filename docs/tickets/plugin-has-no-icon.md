# The plugin has no icon, and the first icon submitted to the directory is permanent

Status: OPEN · Priority: LOW · Type: design decision needed · Cost: none

> Tied to open question 1 in `docs/DECISIONS.md` (directory submission).

## Symptom

`claude plugin validate .` passes with one warning.

## Evidence

```
$ claude plugin validate .
⚠ Found 1 plugin directory warning:

  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING). No icon found in the
    plugin. The validator looked for `icon` in plugin.json and for a file at
    .claude-plugin/icon.png or .svg, assets/icon.png or .svg, or a similar path.
    Fix: Add a square PNG to the plugin folder at .claude-plugin/icon.png, or set
    `icon` in plugin.json to the path of a square PNG or JPEG in the plugin: 512
    to 2048 px on each side, under 2 MB. SVG and WebP are not accepted. That file
    may become the listing icon only once: the first time the plugin is saved or
    submitted in the developer portal. Adding or changing it later does not
    change the icon.

✔ Validation passed
```

Claude Code 2.1.332, run on 2026-11-25.

## Why it matters

It does not block installing from the own marketplace. It matters for a
directory listing, and the validator says the icon is taken once, at the first
save or submission, so it should be chosen before that and not added as an
afterthought.

## Scope to decide

- The owner supplies a square PNG, 512 to 2048 px, under 2 MB, at
  `.claude-plugin/icon.png`.
- OR ship without one until a directory submission is planned.

No code change made by this ticket. It is an observation on the record.
