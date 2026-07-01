# Corridor CI

**No scope, no review.**

Maintainers are getting buried by AI-generated PRs.

Many of those PRs are not malicious. They are just under-specified: too many
files, unclear scope, surprise dependencies, and no obvious stop condition.
Review time gets spent reconstructing what the PR was supposed to do.

Corridor CI moves that work back to the PR author.

It does not try to detect whether a PR was written by an AI. It asks a more
useful question:

> Did the PR declare what it is allowed to change, and did it stay inside that
> boundary?

The point is intentional friction. If someone sends a PR with an agent, the
scope work should happen before maintainer review, not inside maintainer review.

## What It Checks

- A corridor exists, either in `.slime/corridor.md` or the PR body.
- The corridor has a `## Paths` section.
- Changed files stay inside those declared paths.
- Dependency manifest changes are blocked by default.
- Optional: PRs that touch too many files are blocked or warned.

It does not auto-close PRs. Start in `warn` mode, then switch to `fail` when the
policy is accepted by the project.

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

      - uses: shihchengwei-lab/corridor-ci@v1
        with:
          mode: warn
          max_changed_files: 12
```

After the team is ready:

```yaml
      - uses: shihchengwei-lab/corridor-ci@v1
        with:
          mode: fail
          max_changed_files: 12
```

## Corridor Format

Put this in `.slime/corridor.md`, or paste the same sections into the PR body:

```md
# Corridor: rating-widget

## Semantic Delta
- Add a controlled rating input.

## Non-goals
- Do not refactor forms.
- Do not add dependencies.

## Paths
- frontend/src/components/ui/**
- frontend/tests/**

## Stop Condition
- Existing frontend tests still pass.
```

`## Paths` is the hard part. The other sections are reported as warnings when
missing because they make the PR easier to review.

## Inputs

| input | default | meaning |
|---|---:|---|
| `mode` | `fail` | `fail` exits non-zero on issues; `warn` only reports. |
| `source` | `auto` | `auto`, `file`, or `body`. Auto checks file first, then PR body. |
| `corridor_file` | `.slime/corridor.md` | File to read when using file source. |
| `corridor_required` | `true` | Require a corridor. |
| `allow_dependencies` | `false` | Allow dependency manifest changes. |
| `max_changed_files` | `0` | Optional changed-file limit. `0` disables it. |
| `base_ref` | empty | Git diff base ref. Defaults to `origin/${{ github.base_ref }}`. |
| `changed_files` | empty | Optional changed-file list or path to a list file. |

## Philosophy

This is the receiving-side half of agent discipline.

Author-side tools such as Slime Coding help your own agent avoid drifting while
it writes code. Corridor CI helps maintainers reject drift before review when
the PR comes from someone else's agent.

The rule is simple:

> If a PR cannot say where it is allowed to move, maintainers should not spend
> time discovering that boundary by review.

## License

MIT
