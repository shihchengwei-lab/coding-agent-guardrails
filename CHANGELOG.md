# Changelog

Cross-component release ledger for the Guardrails toolkit. Per-component
detail lives in [agentcam/CHANGELOG.md](agentcam/CHANGELOG.md) and
[slime-coding/CHANGELOG.md](slime-coding/CHANGELOG.md); Corridor CI is
tag-driven (see [corridor-ci/docs/RELEASING.md](corridor-ci/docs/RELEASING.md)).

## 2026-07-16 — Agentcam 0.7.0 · Corridor CI v15.0.0

Publishes everything since the `agentcam-v0.6.0` / `corridor-ci-v14.0.0` tags
(PRs #32–#41): the v14 rollout alignment, a full external audit, three fix
rounds, and a mental-model convergence round.

### Agentcam 0.7.0

- Git state and fingerprints computed from the git root — subdirectory runs
  no longer lose run records; `verify`/`handoff` work from subdirectories.
- Session snapshots stored as JSON instead of pickle (legacy pickle sessions
  are discarded on upgrade).
- Redaction and output-risk-scan coverage widened; export bundles no longer
  leak absolute local paths.

### Corridor CI v15.0.0

- **Gate tightening**: `uv.lock`, `setup.py`, `npm-shrinkwrap.json`, and
  `bun.lockb` now count as dependency manifests — PRs touching them require a
  head-bound `Guardrails-Dependency-Approval` comment that v14 did not ask
  for.
- **Removed** the `review_artifact` action input (it could never validate:
  a custom path cannot satisfy its own fingerprint exclusion). The artifact
  path is the fixed contract `.guardrails/review.json`.
- Policy checks fail closed on a missing or malformed head SHA and on
  malformed scope globs; the policy gate re-reads approval comments briefly
  so the comment-after-push race resolves within one run.
- The installer recognizes and auto-upgrades official v13 and v14 workflow
  templates; customized workflows are preserved as before.

### Slime coordinator

- Committed-only deliveries complete on the first Stop; stale delivery state
  self-absorbs after a merge; every block reason states a next step;
  dependency detection mirrors Corridor's list.

### Security notes

- **Removed a code-execution class**: hook-mode session state no longer uses
  pickle. An agent with file-write permission could previously plant a
  snapshot that executed code at the next SessionEnd.
- **Closed redaction gaps**: non-HTTP URL credentials (`postgres://`,
  `mongodb+srv://`, `redis://`, `git+ssh://`) and fine-grained GitHub PATs
  are now redacted; the share-safe export no longer embeds absolute paths.
- **Supply chain**: the PyPI publish action is pinned to an immutable commit
  SHA; all CI workflows carry explicit least-privilege `permissions`.
- **Fail-closed hardening**: approval matching rejects empty head SHAs;
  malformed scope globs match nothing instead of crashing the checker.
- Known, documented limits are unchanged: the review artifact is
  author-controlled evidence, not attestation; hooks are workflow gates, not
  a sandbox; the default PTY backend weakens inline redaction.

### Contract freeze

The following are frozen as of this release and will only change with a
major Corridor version and a migration note:

- `.guardrails/review.json` schema 1 and its fixed path.
- The approval comment formats `Guardrails-Workflow-Approval: <head-sha>`
  and `Guardrails-Dependency-Approval: <head-sha>`.
- The hook JSON contract the coordinator speaks to Claude Code and Codex.
- The invariant that the local `is_dependency_manifest` set mirrors
  Corridor's `DEPENDENCY_GLOBS`.

### Observation period

No structural work is planned next. The trigger for revisiting the artifact
layer's size: if future delivery cycles hit new walls inside the artifact
machinery, or `review.json` is consistently never read during review, the
"shrink the artifact layer, keep the approval layer" redesign gets evaluated.
Until then, usage decides.
