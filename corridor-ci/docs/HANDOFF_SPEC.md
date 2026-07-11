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
Risk: none-detected
```

`<fill in...>`, `n/a`, `tbd`, `todo`, and `not set` are still incomplete and
fail the corridor.

Headings, bold labels, and bullet labels are not fields. For example,
`### Decision`, `**Decision:** #123`, and `- Decision: #123` are invalid.

## Verification Provenance

`Verified` is required handoff context, not proof by itself. A manual command or
check is accepted and labeled `manual`. When an agentcam manifest is committed,
Corridor CI labels it `local-recorded` only if the handoff contains
`[locally recorded by agentcam]`, exact fixed grammar, an integer exit code 0,
matching verification state, and a product fingerprint equal to the current
PR. The legacy `[recorded by agentcam]` marker is rejected.
Placeholders, `n/a`, and unmatched recorded claims are `unverified`
and fail the corridor. Manual checks remain valid and labeled `manual`. Legacy
or hook capture can additionally be labeled `partial` without changing the
verdict.

`manual` and `partial` produce warnings only. `unverified` is an issue and fails
the default action mode.

## Scope

`Scope` is a comma-separated list of paths or glob patterns. Paths are normalized
to forward slashes. Glob matching uses git-style semantics: `*` and `?` never
cross `/`, `**/` spans zero or more directories, and `dir/**` means the
directory and the whole subtree.

`Scope: auto` is rejected. A declared boundary must be independent of the diff
it checks. Match-everything patterns such as `**/*` are rejected for the same
reason.

## Pass Conditions

A report passes when all required fields are present, `Review first` is one of
the changed files, every changed file is covered by the declared scope, the
changed-file limit is not exceeded, and dependency manifest changes are allowed
or absent.

All changes require all five fields. File count is not a proxy for semantic
risk: a one-file policy, authentication, migration, or workflow change still
needs a review boundary.

## Warnings

Warnings never block. Corridor CI warns when:

- `Decision` has no `#123`-style reference and no `http://` or `https://` URL.
- The PR body is more than 60 lines, because the compact handoff is harder to
  find.
- Verification is manual or observation coverage is partial.
