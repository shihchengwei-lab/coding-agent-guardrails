# agentcam design

This document describes the behavior that exists now. Historical experiments
and unimplemented extension points belong in git history, not in the runtime
contract.

## Purpose

agentcam turns an agent's claim into local evidence:

1. snapshot the repository before work;
2. observe the work through the available capture surface;
3. snapshot the repository after work;
4. record changed files, risk flags, command result, and verification runs;
5. produce a review report and five-line handoff draft.

It is an observability tool, not a sandbox, intent classifier, or correctness
proof. Every report states what agentcam could and could not see.

## Storage

Run artifacts live under:

```text
<git_dir>/agentcam/runs/<run_id>/
```

Using the resolved git dir keeps artifacts local, avoids working-tree
self-pollution, and works in worktrees and submodules. A run contains:

- `manifest.json`: machine-readable metadata and evidence;
- `AGENT_RUN_REPORT.md`: human review view;
- raw stdout/stderr logs when a process was wrapped;
- redacted stdout/stderr logs for normal review and export.

Raw logs are never part of the committable export. They are still ordinary
local files and may be captured by backup or cloud-sync software.

## Recording modes

### Wrapped process

`agentcam run -- <argv...>` launches the process directly. Shell syntax is not
interpreted; callers that need a shell invoke it explicitly. The wrapper tees
terminal output to logs, scans raw output for risk patterns, and records the
child exit status.

PIPE is the default non-interactive backend. POSIX pty and Windows ConPTY are
used for interactive terminal behavior where available. PTY modes merge stderr
into stdout and say so in capture metadata.

### Claude Code session hooks

`hook-session-start` snapshots on `SessionStart`; `hook-session-end` writes the
run on `SessionEnd`. State is stored under
`<git_dir>/agentcam/sessions/<session_id>/` and removed at the end. Duplicate
starts preserve the first baseline.

### Codex turn hooks

Codex has no `SessionEnd`. `hook-turn-start` therefore snapshots on
`UserPromptSubmit`, and `hook-turn-end` writes the run on `Stop`, keyed by
`turn_id`. This records every turn rather than only the first turn of a thread.
The root Windows installer wires both events.

Both hook modes always exit 0: recording failure must remain visible as missing
evidence, but must not trap the coding agent in a broken lifecycle hook. Hook
mode sees git state and paths, not terminal output.

## Capture visibility

Every production manifest requires a `capture` block. The report renders the
same data so absence of evidence cannot be mistaken for evidence of absence.

| Mode | Git before/after | Path scan | Output scan | Result with no flags |
|---|---:|---:|---:|---|
| wrap PIPE / PTY | yes | yes | yes | `none-detected` |
| Claude hook | yes | yes | no | `unknown` |
| Codex hook | yes | yes | no | `unknown` |

Internal tool calls, file reads that leave no git-visible trace, and network
egress are outside agentcam's observation surface.

## Git state and no-diff cleanup

Git state comes from `git status --porcelain=v1 -z`, cached and non-cached
diffs, HEAD, branch, and operation markers. NUL-delimited porcelain parsing is
required for spaces, renames, and non-ASCII paths.

A successful run with the same HEAD, porcelain bytes, and content fingerprint
before and after is removed unless the user asked to keep empty runs or output
risk evidence was observed. Discussion-only sessions leave no artifact.

The fingerprint closes the gap where an already-dirty file changes content but
keeps the same porcelain status.

## Risk flags

Risk flags are review-routing heuristics. The only flag levels are `HIGH` and
`MEDIUM`; there is no `LOW` flag.

- `HIGH`: tracked deletion, secret-like filename, auth/security/infra paths,
  destructive command output, conflict markers, or force-push output.
- `MEDIUM`: dependency/build/container manifests and known suspicious output
  patterns that warrant review but are not inherently destructive.

When no flag fires:

- full wrap capture reports `NONE_DETECTED` in evidence and `none-detected` in
  the handoff;
- partial hook capture reports `unknown` in the handoff and report verdict.

`NONE_DETECTED` means only that the enabled heuristics found no match.

## Scanner identity

The scanner uses one built-in ruleset. `builtin_ruleset_sha256()` hashes the
exact ordered path rules plus output regex patterns and flags. Every production
manifest requires a compact `ruleset` block:

```json
{
  "builtin_ruleset_id": "agentcam-default",
  "builtin_ruleset_version": "<agentcam version>",
  "rules_sha256": "sha256:<hex>"
}
```

There is no custom-rules parameter or unimplemented YAML loader. If custom
rules become a real user requirement, they should arrive as a complete feature
with loading, validation, provenance, and tests.

## Redaction

Redaction is best-effort defense in depth, not a data-loss-prevention guarantee.
The streaming redactor buffers boundary-sensitive material so secrets split
across chunks are still detected. Secret-like filenames are redacted in every
shareable Markdown/JSON surface, not only in logs.

The output scanner reads raw logs because redaction may hide the signal being
scanned. Risk evidence contains only the rule label and line number, never the
matched raw text.

## Report input contract

`render_report` accepts exactly one `ReportBundle`, containing the manifest,
before/after git states, risk flags, and dependency changes. `RunManifest`
requires both capture visibility and scanner provenance. There are no optional
legacy shapes in the runtime API.

The manifest schema remains `0.1`; all current producers write the same required
blocks. Consumers should treat malformed author-controlled JSON as untrusted
input and degrade safely.

## Dependency evidence

The dependency probe compares supported manifests against HEAD and reports
direct dependency additions, removals, and version changes for pip,
PEP 621/Poetry, and npm. It is review evidence; it does not infer whether a
dependency is justified.

## Verification and handoff

`agentcam verify -- <command>` runs the check itself and records argv, exit code,
and duration. A check is recorded as passing only when the observed exit code is
zero. During an active hook recording, verification is stashed into that
recording and merged when it ends.

`agentcam handoff` derives Scope, Review first, Verified, and Risk from the
manifest. Decision remains an author field because agentcam cannot know why the
change was chosen. Without a matching passed check, Verified remains a fill-in.

`agentcam export ... --files` writes only redacted, committable evidence.
Corridor CI independently cross-checks recorded verification claims.

## Exit behavior

Wrapped subprocess results are normalized to wrapper exit 0 for child success
and 1 for child failure. The raw return code, platform interpretation, and known
Windows NTSTATUS/POSIX signal detail remain in the manifest and report.

Hook commands return 0 even on internal recording errors. Other CLI commands
return non-zero on invalid input, missing runs, failed checks, or export errors.

## Security boundary

agentcam does not prevent commands, network access, or filesystem writes. It
cannot observe actions that leave neither captured output nor git-visible
changes. An actor that can rewrite `.git/agentcam` can tamper with local
evidence. Use OS isolation, repository permissions, and CI for enforcement;
use agentcam to make ordinary agent work reviewable.
