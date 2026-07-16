# Corridor CI v14

Corridor CI is the receiving-side gate for the single Guardrails review
artifact. It does not parse the pull-request body and does not execute PR code.
The author may describe the PR normally.

The installed coordinator creates:

```text
.guardrails/review.json
```

Corridor independently compares that artifact with the current PR diff before
a maintainer spends review attention.

## Workflow

After the v14 release, pin the immutable tag:

```yaml
name: Corridor CI

on:
  pull_request:
    types: [opened, synchronize, reopened, edited]

permissions:
  contents: read

jobs:
  corridor:
    name: Corridor
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: shihchengwei-lab/coding-agent-guardrails/corridor-ci@corridor-ci-v14.0.0
```

The default mode is `fail`. A workflow is not a merge gate until `Corridor` is
a required check in branch protection or a ruleset.

## What it checks

- The artifact exists, is no larger than 1 MiB, and matches schema 1.
- Its product fingerprint equals the current PR product diff.
- Its declared scope covers every product file.
- `review_first` names an actual changed product file.
- Recorded checks use a non-boolean integer exit code `0`, valid argv, and a
  state fingerprint equal to the current product state.
- The declared risk is not lower than the risk Corridor derives from paths,
  statuses, dependency manifests, and workflow changes.
- High-risk work has a confirmation bound to the same product fingerprint.
- Dependency and workflow changes have the required GitHub approval bound to
  the current full head SHA.

`.guardrails/review.json` is listed as a touched file but excluded from the
product fingerprint and scope comparison. This lets the artifact describe the
product without recursively changing the state it binds.

`structural-only`, partial capture, and unavailable terminal output are visible
warnings. They never pretend behavioral tests ran. Malformed, stale, tampered,
or under-reported evidence is an issue and fails in the default mode.

All artifact strings are Markdown-escaped before reporting. A sticky comment,
when enabled, updates only a comment created by `github-actions[bot]`.

## Inputs

| input | default | meaning |
|---|---:|---|
| `mode` | `fail` | `fail` exits non-zero on issues; `warn` only reports. |
| `comment` | `false` | Upsert the report as a bot-owned sticky PR comment. |

Sticky comments require `pull-requests: write`; the default action needs only
`contents: read`.

The schema and invariants are documented in
[`docs/HANDOFF_SPEC.md`](docs/HANDOFF_SPEC.md). The name is retained so old
links do not break; v14 has no PR-body handoff grammar.

## Boundary

The artifact is author-controlled local evidence, not third-party attestation.
State binding makes stale or mismatched claims observable. The default-branch
Policy Gate is the separate control that prevents a PR from replacing its own
enforcement workflow and checker.

## License

MIT.
