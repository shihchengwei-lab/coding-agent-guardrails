# Corridor CI

**No scope, no review.**

Maintainers do not need every PR description to be longer. A PR can be vague or
verbose and still leave the same problem: nobody knows where the change was
supposed to stop.

Corridor CI is a small GitHub Action that asks a non-trivial PR to draw a narrow
review corridor before maintainer attention:

```md
Decision: #123
Scope: pkg/parser/*, tests/parser/*
Review first: pkg/parser/links.py
Verified: pytest tests/parser
Risk: low
```

`Decision` points to where the why already lives: an issue, discussion, RFC,
spec, bug reproduction, maintainer request, or a clearly small fix.

`Scope` is the restraint mechanism. With explicit paths or globs, Corridor CI
compares the actual diff against the declared corridor and warns or fails when
the PR touched more than it said it would.

`Scope: auto` is still available when a project only wants review visibility. It
turns the actual changed files into the review boundary, but it does not
restrain the diff.

It is not an AI detector, a spam score, or an AI reviewer. It does not care who
wrote the code. It only asks:

> Did the PR declare a narrow review corridor?
> Did the actual diff stay inside it?

![Before and after Corridor CI review handoff](docs/assets/corridor-ci-before-after.svg)

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

      - uses: shihchengwei-lab/corridor-ci@v8
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
Scope: pkg/parser/*, tests/parser/*
Review first: pkg/parser/links.py
Verified: pytest tests/parser
Risk: low
```

`Decision` can be an issue, discussion, RFC, spec, bug reproduction, maintainer
request, or small self-contained fix.

Use explicit paths or globs when you want the PR to stay inside a declared
corridor:

```md
Scope: pkg/parser/*, tests/parser/*
```

Use `Scope: auto` only when you want low-friction review visibility. It uses the
actual changed files as the review boundary.

`Review first` must be one of the changed files.

## What It Checks

- Required handoff fields exist.
- Explicit `Scope` paths or globs cover the changed files.
- `Scope: auto` resolves to the actual changed files when chosen.
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
| `allow_dependencies` | `false` | Allow dependency manifest changes. |

## Philosophy

Corridor CI is a receiving-side gate with one shaping rule: draw the corridor
before asking for review.

It does not decide whether a PR is good. It makes the author state the review
boundary before asking a maintainer to spend attention. That is especially
useful for agent-written PRs, where the failure mode is often touching more than
the task needed.

The rule is simple:

> If a PR cannot say where it intended to move, maintainers should not spend
> time discovering that boundary by review.

## License

MIT
