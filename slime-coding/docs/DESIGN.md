# Slime Coding design

The root installer copies a versioned runtime to
`<git-dir>/guardrails/runtime/<revision>/` and wires a single coordinator into
Claude Code and Codex. Hook commands use absolute paths to the installed
interpreter and runtime, so the source checkout is not a runtime dependency.

## State

- `config.json`: trusted check argv and timeouts.
- `deliveries/<branch-hash>/scope.json`: outcome, allowed paths, base commit,
  and reasoned scope expansions.
- turn baselines: Git state needed to exclude unchanged pre-existing dirt and
  detect staged, committed, renamed, deleted, and untracked changes.
- pending approval: nonce plus branch/delivery/product binding and confirmation
  hash; no raw prompt.

All runtime state is Git-local. The only generated working-tree file is
`.guardrails/review.json`.

## Stop transaction

Stop calculates one delivery delta, checks the declared paths, runs structural
and configured checks once, derives risk from that same delta, requires a
matching high-risk confirmation when needed, finalizes Agentcam, and atomically
writes the review artifact. State is cleared only after every step succeeds.

Direct edit hooks can block before writing. Shell hooks cannot reliably predict
all side effects, so they compare the delta immediately after Bash and Stop
does the final comparison. That is observation, not filesystem isolation.

## Trust boundary

Repository Markdown cannot authorize executable commands. Trusted commands and
the installed runtime live under the Git directory. Pull-request policy runs
from the default branch and treats PR commits as data. These choices prevent a
PR from changing the checker it is currently asking to pass; they do not defend
against a malicious administrator with control of the machine and repository.
