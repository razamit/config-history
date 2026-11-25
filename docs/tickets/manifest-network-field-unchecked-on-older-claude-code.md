# The manifest's `network` field has not been checked against older Claude Code versions

Status: OPEN · Priority: MEDIUM · Type: compatibility, unverified claim · Cost: none

## Symptom

`.claude-plugin/plugin.json` declares the hosts the install downloads from. The
agent that added the field reported that Claude Code versions up to 2.1.75 may
reject a manifest containing it. That statement was not checked against the
docs or an older build.

## Evidence

```
$ sed -n 20,25p .claude-plugin/plugin.json
  "network": {
    "hosts": [
      "pypi.org",
      "files.pythonhosted.org"
    ]
  }

$ claude plugin validate .        # Claude Code 2.1.332
Hosts: files.pythonhosted.org (declared), pypi.org (declared)
✔ Validation passed
```

Fix-pass report, 2026-11-25, under "Not verified": "Claude Code versions up to
2.1.75 may reject the new `network` field."

Only 2.1.332 was available on this machine.

## Why it matters

If an older client rejects the manifest, the plugin fails to load there with no
fallback. If older clients ignore unknown fields, there is no problem. Which of
the two is true is not known.

## Scope to decide

- Read the plugin reference and changelog for when `network` was introduced and
  how earlier versions treat unknown manifest fields, and close this if they
  are ignored.
- OR state a minimum Claude Code version in the README and manifest
  description.
- OR drop the field, accepting the validator's note about undeclared hosts.

No code change made by this ticket. It is an observation on the record.
