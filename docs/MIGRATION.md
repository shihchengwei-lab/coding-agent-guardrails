# Guardrails low-friction migration

This is a deliberate breaking migration. It removes compatibility paths that
made the user operate internal workflow concepts or allowed old evidence to
look current.

## Upgrade

Run the root installer again from the repository worktree root:

```bash
/path/to/coding-agent-guardrails/install.sh /path/to/project
```

```powershell
& C:\path\to\coding-agent-guardrails\install.ps1 -Project C:\path\to\project
```

The installer replaces only provably managed hook blocks and runtime files.
User hooks, custom workflows, trusted check configuration, Agentcam history,
and existing `.slime/` data are preserved. `.slime/` becomes archived state:
the new runtime neither migrates nor reads it.

After the v15 release rollout, the managed Corridor workflow pins
`corridor-ci-v15.0.0`. Official v13 and v14 templates are recognized and
upgraded automatically; a customized workflow is preserved and `doctor`
reports the required manual update.

## Agentcam 0.6 to 0.7

Re-run the root installer. Hook-mode session snapshots changed from pickle to
JSON: an in-flight session started under 0.6.x is discarded rather than
loaded, so finish or discard in-progress sessions first if their turn record
matters. Subdirectory invocations, redaction coverage, and export path
handling are fixed; no user action is needed for those.

## Corridor CI v14 to v15

The dependency-approval surface grew: PRs touching `uv.lock`, `setup.py`,
`npm-shrinkwrap.json`, or `bun.lockb` now require the head-bound
`Guardrails-Dependency-Approval` comment. The `review_artifact` action input
was removed — it could never pass validation; the artifact path is the fixed
contract `.guardrails/review.json`. The policy gate briefly re-reads approval
comments, so an approval posted right after the push lands in the same run.

## Removed daily workflow

Do not create or edit `.slime/corridor.md` or `.slime/PRUNED.md`. Rigor,
Evidence, Stop Condition, PRUNED entries, `/slime-corridor`, and `/slime-prune`
are no longer runtime interfaces.

Do not run `agentcam verify`, `agentcam handoff`, or `agentcam export` for the
integrated flow, and do not paste the old five-line handoff into the PR body.
The coordinator now runs trusted checks and creates one state-bound file:

```text
.guardrails/review.json
```

The PR body is free-form. Commit the artifact when the user asks for the normal
commit or PR operation; Guardrails never stages or commits automatically.

## Trusted checks

Existing schema-1 config under `<git-dir>/guardrails/config.json` is reused.
If no primary check exists, the installer configures one only when a single
root ecosystem is unambiguous. Otherwise the runtime reports
`structural-only`.

Maintenance commands remain available:

```bash
guardrails check set primary -- python -m pytest -q
guardrails check remove primary
guardrails doctor
```

Repository Markdown and the old `SLIME_TEST_CMD` or `SLIME_TYPECHECK_CMD`
variables never authorize shell execution.

## Agentcam 0.5 to 0.6

Agentcam 0.6 is finalized by the coordinator after checks and high-risk
confirmation succeed. The review artifact binds its records to the final
product fingerprint. Standalone Agentcam commands remain available for
diagnostics, but they are not user steps in the integrated workflow.

## Corridor CI v13 to v14

Corridor v14 reads only `.guardrails/review.json`. It does not parse the PR body
or accept a five-line fallback. Old Agentcam exports and locally recorded
markers cannot satisfy the v14 gate.

Dependency and workflow changes still require an OWNER/MEMBER approval comment
bound to the current full head SHA. A high-risk local confirmation can authorize
the agent to sync that comment after the PR exists; if `gh` is unavailable or
the SHA does not match, CI shows the exact manual comment instead.
