# Corridor CI Handoff Spec

Corridor CI reads a compact handoff from the pull request body. The grammar is
strict so other tools can generate the same shape reliably.

## Fields

The handoff has five required fields, each with exactly one label (matched
case-insensitively). The first occurrence wins. There are no aliases.

- `Decision`
- `Scope`
- `Review first`
- `Verified`
- `Risk`

Each field must be a single plain line:

```md
Decision: #123
Scope: pkg/parser/*, tests/parser/*
Review first: pkg/parser/links.py
Verified: pytest tests/parser
Risk: low
```

Headings, bold labels, and bullet labels are not fields. For example,
`### Decision`, `**Decision:** #123`, and `- Decision: #123` are invalid.

## Verification Provenance

`Verified` is required handoff context, not proof by itself. A manual command or
check is accepted and labeled `manual`. When an agentcam manifest is committed,
Corridor CI labels it `recorded` only if the handoff contains
`[recorded by agentcam]` and an exact `command (exit 0)` match from that
manifest. Placeholders, `n/a`, and unmatched recorded claims are `unverified`.
Legacy or hook capture can additionally be labeled `partial`.

These labels produce warnings only. They never change the pass conditions or
the action exit code.

## Scope

`Scope` is a comma-separated list of paths or glob patterns. Paths are normalized
to forward slashes. Glob matching uses git-style semantics: `*` and `?` never
cross `/`, `**/` spans zero or more directories, and `dir/**` means the
directory and the whole subtree.

`Scope: auto` is also accepted. It uses the changed files as the declared review
boundary.

## Pass Conditions

A report passes when all required fields are present, `Review first` is one of
the changed files, every changed file is covered by the declared scope, the
changed-file limit is not exceeded, and dependency manifest changes are allowed
or absent.

If no handoff was attempted, small PRs can pass only when
`small_change_max_files` is enabled, the changed-file count is within that
limit, and no dependency manifest changed.

## Warnings

Warnings never block. Corridor CI warns when:

- A declared scope pattern is `*`, `**`, or `**/*`, because the corridor carries
  no information.
- `Decision` has no `#123`-style reference and no `http://` or `https://` URL.
- The PR body is more than 60 lines, because the compact handoff is harder to
  find.
