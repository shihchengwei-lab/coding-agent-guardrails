# Corridor CI

**No scope, no review.**

Maintainers are getting buried by low-context PRs.

Corridor CI is a small GitHub Action that asks a PR to declare its review
boundary before maintainer review:

```md
Decision: #123 or small fix
Scope: auto
Review first: path/to/file
Verified: make test
Risk: none
```

Then it checks the actual diff against that boundary.

It is not an AI detector, a spam score, or an AI reviewer. It does not care who
wrote the code. It only asks:

> Did the PR say what should be reviewed?
> Did the diff stay inside that scope?

## Quick Start

```yaml
name: Corridor CI

on:
  pull_request:

jobs:
  corridor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: shihchengwei-lab/corridor-ci@v7
        with:
          mode: warn
          small_change_max_files: 1
          max_changed_files: 12
```

Start with `mode: warn`. Switch to `mode: fail` after the project accepts the
rule.

Add this to the PR body:

```md
Decision: #123
Scope: auto
Review first: pkg/example.go
Verified: make test
Risk: none
```

`Decision` can be an issue, discussion, RFC, spec, bug reproduction, maintainer
request, or small self-contained fix.

`Scope: auto` uses the actual changed files as the declared boundary.

`Review first` must be one of the changed files.

## What It Checks

- Required handoff fields exist.
- Changed files stay inside `Scope`.
- `Review first` points to a changed file.
- Dependency manifest changes are blocked unless explicitly allowed.
- PRs over `max_changed_files` are blocked or warned.
- Tiny PRs can skip the handoff when `small_change_max_files` allows it.

If the handoff is missing or incomplete, the CI summary includes a copyable blank
handoff.

Every run writes a GitHub step summary for maintainers.

## Inputs

| input | default | meaning |
|---|---:|---|
| `mode` | `warn` | `fail` exits non-zero on issues; `warn` only reports. |
| `small_change_max_files` | `0` | Allow no-handoff small changes up to this file count. `0` disables it. |
| `max_changed_files` | `0` | Optional changed-file limit. `0` disables it. |

## Philosophy

Corridor CI is a receiving-side gate.

It does not decide whether a PR is good. It makes the author state the review
boundary before asking a maintainer to spend attention.

The rule is simple:

> If a PR cannot say where it is allowed to move, maintainers should not spend
> time discovering that boundary by review.

## License

MIT
