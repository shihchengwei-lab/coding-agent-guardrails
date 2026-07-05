# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**CI green is not done. Done is when a human can take over.**

Coding agents finish the task. Tests pass. The check turns green. Then a human
inherits the diff — reads it, owns it, maintains it. This toolkit sits on the
agent's side of that handoff: one install wires four tools that cover the
corridor from "agent starts typing" to "human presses merge".

| Stage | Tool | What it adds |
|---|---|---|
| Before the agent starts | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) rules | One unified discipline block in your `CLAUDE.md` ([templates/DISCIPLINE.md](templates/DISCIPLINE.md)): smallest readable change, minimal semantic drift, stop when done. |
| While the agent works | [slime-coding](slime-coding/) hooks | Automatic gates that hold the agent inside the corridor it declared before editing. |
| After the agent claims done | [agentcam](agentcam/) | Records what actually changed — files, risk flags, diff stat — and drafts the PR handoff from that record. |
| Before a human reviews | [corridor-ci](corridor-ci/) | Validates the five-line handoff against the actual diff and appends the recorded evidence to the PR report. |

## Install (one command)

```bash
git clone <this repo> ~/guardrails
~/guardrails/install.sh /path/to/your/project
pip install agentcam
```

Re-running is safe. The installer wires the discipline block into
`CLAUDE.md`, installs the slime-coding hooks, and drops a starter
corridor-ci workflow (skipping any you already have).

## The loop

The tools feed each other — that is the point of the package:

1. **Record** — `agentcam run -- <agent command>` (or work in Claude Code
   with the slime hooks active). Everything the agent changed is recorded
   under `.git/agentcam/runs/`.
2. **Hand off** — `agentcam handoff` prints the five-line corridor handoff
   drafted from the record. Paste it into the PR body, then fill in
   `Decision` and `Verified` — the two lines only the author can know.
3. **Attach evidence** — `agentcam export latest --files .agentcam/`
   writes the redacted run record in committable form; commit it with
   the PR.
4. **Gate** — corridor-ci on the PR validates the handoff against the
   actual diff and appends the recorded evidence (risk flags, diff stat)
   to its report. Evidence is display-only: it informs the reviewer, it
   never flips the check.

Every tool also works standalone — each subdirectory has its own README.

## Versioning

One repo, four tools, so release tags are prefixed per tool:
`agentcam-v0.3.0`, `corridor-ci-v11`, and so on. Earlier releases
(`v0.2.0`, `v10`, …) live in each tool's original repository.

## History

Each tool started as its own repository and was imported here with full
commit history — `git log` inside any subdirectory goes back to that
tool's first commit.

## License

MIT, for the toolkit and for every tool in it.
