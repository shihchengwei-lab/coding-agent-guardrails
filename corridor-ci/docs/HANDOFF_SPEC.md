# Corridor CI v15 review artifact specification

The historical filename is retained for stable links. Corridor CI v15 has no
fixed PR-body handoff. It reads exactly one JSON artifact at
`.guardrails/review.json` by default.

## Shape

```json
{
  "schema": 1,
  "generator": {
    "agentcam_version": "0.7.0",
    "runtime_revision": "revision"
  },
  "delivery": {
    "base_commit": "sha-or-null",
    "product_fingerprint": "sha256",
    "changed_files": [{"path": "src/app.py", "status": "modified"}],
    "outcomes": ["observable result"],
    "scope": ["src/app.py", "tests/test_app.py"],
    "scope_changes": [],
    "review_first": "src/app.py",
    "risk": "none-detected"
  },
  "verification": {
    "level": "recorded",
    "checks": [{
      "id": "primary",
      "argv": ["python", "-m", "pytest", "-q"],
      "exit_code": 0,
      "duration_ms": 1234,
      "state_fingerprint": "sha256"
    }]
  },
  "capture": {
    "terminal": "unavailable",
    "coverage": "partial"
  },
  "approval": null
}
```

The file must be UTF-8 JSON, no larger than 1 MiB, with `schema` equal to the
integer `1`. Commands are argv arrays; repository text never supplies shell
syntax for execution.

## Product state

The product fingerprint is derived from current product paths and statuses.
The artifact itself is excluded from that fingerprint and from scope coverage,
but remains visible in the PR touched-file list.

Every changed product file must be covered by `delivery.scope`.
`review_first` must be one of those product files. Empty and match-all scope is
invalid.

The accepted risk values are `high`, `medium`, `none-detected`, and `unknown`.
Corridor recomputes a minimum risk; the artifact may be more cautious but not
less cautious.

## Verification

`verification.level` is either:

- `recorded`: every listed check has a string ID, nonempty string argv, integer
  exit code `0` (a JSON boolean is not an integer result), duration, and current
  state fingerprint.
- `structural-only`: no reliable behavioral test was configured. This passes
  with a warning and must not contain a fabricated passing primary check.

Partial capture or unavailable terminal output is a warning only.

## High-risk approval

High-risk work requires an approval object bound to the identical product
fingerprint. The local coordinator accepts only an exact user prompt or the
TTY-only fallback and stores a confirmation hash, never the raw prompt.

Dependency and workflow changes additionally require an OWNER/MEMBER GitHub
comment containing the current full PR head SHA:

```text
Guardrails-Dependency-Approval: <full-head-sha>
Guardrails-Workflow-Approval: <full-head-sha>
```

New commits invalidate earlier approvals. The policy gate re-reads comments
briefly before failing, so an approval posted right after the push is picked
up in the same run; an approval posted later needs a normal re-run of the
check.

## Report safety

Artifact-controlled text is Markdown-escaped. Malformed shapes safely become
issues rather than exceptions. Sticky comment updates are restricted to the
bot's own previous comment.
