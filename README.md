# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**Install once. Then ask your coding agent to work as usual.**

Guardrails keeps the agent inside a declared file boundary, runs the repository's
trusted checks at Stop, records the final state, and writes one review artifact:
`.guardrails/review.json`. You do not edit a corridor, choose a risk tier, run
Agentcam commands, or paste a fixed PR handoff.

## Why a Vibe-Built Tool Needs Guardrails

This project is mostly implemented by coding agents. I am not a software
engineer, I do not write code, and I cannot judge a diff line by line. In
practice, I usually do not inspect much: if the benchmark looks good, the tool
runs, or the game moves, I tend to let it move forward.

That is the starting point. I use these tools loosely, and I may not even use
this whole toolkit consistently myself. The contradiction is the point: I vibed
together a tool for limiting vibe coding. The problem is also real. When coding
agents produce a lot of code quickly, the risk often lands in the handoff: what
changed, whether checks really ran, and whether the next person can take over.
Every tool here does one job: turn "trust me" into a recorded fact.

For ordinary changes the daily flow is:

```text
ask the agent to make a change
→ agent works
→ Stop checks scope, tests, risk, and final state
→ ask the agent to commit or open a PR as you normally would
```

For an objectively high-risk change, Stop asks for one exact confirmation such
as `確認高風險變更 7F3A2C`. The nonce is bound to the current product state;
another product edit invalidates it.

## Install

```bash
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails ~/guardrails
~/guardrails/install.sh /path/to/your/project
```

```powershell
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails $HOME\guardrails
& $HOME\guardrails\install.ps1 -Project C:\path\to\your\project
```

The target must be a Git worktree root and needs Python 3.11+. The installer
creates a versioned runtime under `<git-dir>/guardrails/`, installs one
coordinator hook for Claude Code and Codex, and adds repo-local `guardrails`
launchers. The toolkit checkout may be moved or deleted afterward.

If exactly one supported test ecosystem is clear at the repository root,
Guardrails configures its primary test automatically: pytest, Node, Cargo, Go,
or Flutter. If detection is ambiguous, Stop still runs `git diff --check` and
reports `structural-only`; it does not guess or pretend tests ran.

Existing user hooks and trusted checks are preserved. Old `.slime/` data is
preserved as archived state but is no longer read. Managed files are updated
only when ownership can be proved; custom content is preserved with a warning.

## What happens automatically

Before the first product edit, the installed agent instruction makes the agent
store its intended outcome and paths outside the working tree. Direct edits are
checked before writing. Shell writes can only be detected immediately after the
shell call and are checked again at Stop.

At Stop, the single coordinator performs this sequence once:

1. Calculate the branch delivery delta, excluding unchanged pre-existing dirt.
2. Require every product file to be inside the agent's declared scope.
3. Run `git diff --check` and the configured trusted checks.
4. Derive risk from paths, file statuses, dependency changes, and Agentcam.
5. Require the state-bound confirmation when risk is high.
6. Finalize the local Agentcam record and atomically write
   `.guardrails/review.json`.

The artifact records changed files, scope changes, checks, risk, capture
coverage, and the product fingerprint. Guardrails never stages, commits,
pushes, opens a PR, or merges on its own. When you ask the agent to commit or
open a PR, its managed instruction includes the artifact in that normal work.

Corridor CI reads only the artifact. The PR body is free-form. It independently
recomputes the PR product state, scope coverage, risk floor, and recorded check
binding. Dependency and workflow changes also need a GitHub approval comment
bound to the current head SHA; after a confirmed high-risk change the agent can
sync that comment after the PR exists.

## The mental model

You only ever hold two concepts. The agent **declares its scope** before the
first edit, and you **type the confirmation phrase** when a change is
high-risk. Everything else — turns, deliveries, fingerprints, the artifact's
internal shape — is machinery the hooks run for you, and when it stops you it
says why and what to do next.

The two layers do different jobs. The review artifact is the author's own
evidence: it keeps an honest agent honest and gives a reviewer one place to
look, but its author controls it. The security boundary is elsewhere — the
head-SHA-bound GitHub approval comments, the base-branch policy gate, and
ultimately the OS permissions the agent runs under.

## What the user may operate

These are maintenance commands, not daily workflow steps:

```bash
./guardrails doctor
./guardrails doctor --remote
./guardrails check set primary -- python -m pytest -q
./guardrails check remove primary
./guardrails uninstall --dry-run
./guardrails uninstall
./guardrails uninstall --purge-state  # also remove retained local history/config
```

If a host cannot expose the original user prompt to hooks, the only fallback is
`guardrails approve <nonce>`. It requires a TTY and requires the human to type
the complete confirmation phrase again; a non-interactive agent shell cannot
approve itself.

## Boundaries

- Hooks are workflow gates, not an OS sandbox or filesystem sandbox. Direct edits are checked
  before writing; shell side effects are detected afterward. OS permissions or
  a sandbox remain the hard boundary.
- The review artifact is author-controlled local evidence bound to the final
  product state, not third-party attestation.
- `structural-only` means no reliable test command was found. It is a visible
  warning, not evidence that behavior is correct.
- Guardrails cannot judge product quality or replace human review.
- A workflow is not a merge gate until repository rules make `Policy Gate`,
  `Corridor`, and the relevant tests required checks.
- The threat model prevents accidental drift and self-modifying PR policy; it
  does not defend against a malicious repository administrator with full local
  and GitHub control.

See [the migration guide](docs/MIGRATION.md) for the breaking low-friction
upgrade. Each component also has its own README:
[Agentcam](agentcam/), [Slime coordinator](slime-coding/),
[Corridor CI](corridor-ci/), and [kiss-my-diff](kiss-my-diff/).

## Versioning

The low-friction line is Agentcam `0.6.0` and Corridor CI `v14.0.0`. Release
tags are prefixed per component: `agentcam-v0.6.0` and
`corridor-ci-v14.0.0`. Installed workflows pin that immutable Corridor release.

## License

MIT.
