# Example: agent edits an auth path (HIGH)

This example shows what `AGENT_RUN_REPORT.md` looks like when the wrapped
agent modifies a file under an `auth` segment — one of agentcam's HIGH risk
heuristics.

## Scenario

A developer asks Claude Code to add rate limiting to the login endpoint:

```bash
agentcam run --name claude-rate-limit-login -- claude "add rate limiting to the login endpoint"
```

Claude Code edits `src/auth/login.py` (and only that file). The wrapped
process exits 0 (Claude reports success). agentcam produces the report below.

## What the report does

- **Verdict: HIGH** — because `src/auth/login.py` matches the `auth`
  segment heuristic.
- **Risk Flags** cite the matched rule and the file.
- **Changed Files** lists the file as `unstaged_modified`.
- **Rollback Notes** offers a safe path back, since the working tree was
  clean before the run.

## What the report does NOT claim

- It does *not* say the change was malicious or wrong. The auth-path
  heuristic only says "this area is sensitive enough that a human should
  read the diff before merging."
- It does *not* run the diff through any LLM judgment. Heuristics only.
- It does *not* block the change. agentcam is a flight recorder, not a
  gate.

## How `expected-report.md` was generated

It was captured live on 2026-05-16 by:

1. Creating a temporary git repo with one initial commit and
   `src/auth/login.py` already tracked.
2. Running `agentcam run --name claude-rate-limit-login -- python -c
   "<inline script appending rate-limit code to src/auth/login.py>"`.
3. Reading the resulting `AGENT_RUN_REPORT.md` from
   `.git/agentcam/runs/<run_id>/` and committing it here verbatim.

The only edit to the captured output: the `Command:` field was abbreviated
for readability (the full inline Python script is multi-line and noisy).
Everything else — verdict, risk flags, changed files, diff stat, exit
detail, rollback notes, log paths — is the verbatim output of agentcam 0.1.0.

## See also

- `expected-report.md` — the rendered report
- `../../docs/design.md` § 7 — why segment matching, not substring
- `../../docs/design.md` § 12 — secret-like filename redaction (not
  triggered in this example, but referenced in the section about
  `Changed Files` redaction)
