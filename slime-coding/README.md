# Slime Coding Coordinator

Slime Coding is the local workflow boundary inside Coding Agent Guardrails. It
does not add user-facing Markdown, commands, rigor levels, or pruning logs.
After the root installer runs, ordinary use requires no Guardrails operation.

## Runtime flow

One versioned coordinator handles both Claude Code and Codex:

```text
UserPromptSubmit → capture turn baseline and high-risk confirmation
PreToolUse       → check direct-edit paths before writing
PostToolUse Bash → detect out-of-scope shell writes immediately afterward
Stop             → scope, checks, risk, confirmation, record, artifact
SessionEnd       → cleanup only
```

Before its first product edit, the agent calls the internal scope interface:

```bash
guardrails internal scope set \
  --outcome "observable result" \
  --path src/app.py \
  --path tests/test_app.py
```

If another path becomes necessary, the agent records the reason before editing:

```bash
guardrails internal scope add \
  --path src/shared.py \
  --reason "existing validation is owned here"
```

These are agent-internal operations documented in the installed discipline,
not steps for the user. State lives under
`<git-dir>/guardrails/deliveries/` and never enters the working tree.

At Stop, the coordinator calculates the branch delivery delta, checks scope,
runs `git diff --check`, runs configured checks once, derives risk, finalizes
Agentcam, and atomically writes `.guardrails/review.json`. It clears turn state
only after success. A blocked Stop keeps enough state to retry.

## Checks

Trusted commands live outside the repository content in
`<git-dir>/guardrails/config.json` and are executed as argv with `shell=False`.
The installer preserves existing configuration and only auto-detects a primary
check when exactly one root ecosystem is unambiguous.

```bash
guardrails check set primary -- python -m pytest -q
guardrails check remove primary
guardrails doctor
```

Without a primary check, Stop runs only `git diff --check` and records
`structural-only`. A configured check that fails, times out, or cannot execute
blocks completion.

## High-risk confirmation

High risk is derived from objective signals such as dependency manifests,
workflows, deletions, authentication/credential paths, infrastructure paths,
and Agentcam HIGH signals. Stop gives the user one exact phrase:

```text
確認高風險變更 7F3A2C
```

The confirmation is bound to branch, delivery, and product fingerprint. A
later product edit invalidates it. The runtime stores only a confirmation hash,
not the raw user prompt. An agent cannot approve through a non-interactive
shell; `guardrails approve <nonce>` is a TTY-only host fallback.

## Boundary

This is not a filesystem sandbox. Direct edits are checked before writing;
shell side effects are visible only afterward. OS permissions and sandboxing
remain the hard security boundary. Hooks are intended to catch drift and false
completion, not a malicious actor with full control of the repository and
runtime.

Historical corridor, Rigor, Evidence, PRUNED, slash-command, and standalone
Slime installer interfaces were removed from the active runtime. Existing
`.slime/` directories are preserved as archived user data and ignored.

The historical benchmark remains in [`benchmark/`](benchmark/) and is tied to
its immutable discipline fixture; it is not a claim about this later runtime.

## License

MIT.
