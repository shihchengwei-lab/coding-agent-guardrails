# Corridor CI Handoff Spec

Corridor CI reads a compact handoff from the pull request body. The grammar is
strict so other tools can generate the same shape reliably.

## Fields

The handoff has five required fields. The first occurrence wins.

| canonical field | accepted labels |
|---|---|
| `Decision` | `decision`, `issue`, `context` |
| `Scope` | `scope`, `paths`, `touched paths` |
| `Review first` | `review first`, `review-first`, `review_first` |
| `Verified` | `verified`, `verification` |
| `Risk` | `risk` |

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

## Scope

`Scope` is a comma-separated list of paths or glob patterns. Paths are normalized
to forward slashes. Glob matching uses Python `fnmatch` semantics, where `*`
also crosses `/`. `dir/**` means the directory and the whole subtree.

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
