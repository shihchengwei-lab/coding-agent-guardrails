# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**CI green is not done. Done is when a human can take over.**

Coding agents finish the task. Tests pass. The check turns green. Then a human
inherits the diff — reads it, owns it, maintains it. This toolkit sits on the
agent's side of that handoff: one install wires four tools that cover the
corridor from "agent starts typing" to "human presses merge".

| Stage | Tool | What it adds |
|---|---|---|
| Before the agent starts | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) rules | One unified discipline block in your `CLAUDE.md` / `AGENTS.md` ([templates/DISCIPLINE.md](templates/DISCIPLINE.md)): smallest readable change, minimal semantic drift, stop when done. |
| While the agent works | [slime-coding](slime-coding/) hooks | Automatic gates that hold the agent inside the corridor it declared before editing. |
| After the agent claims done | [agentcam](agentcam/) | Records what actually changed — files, risk flags, diff stat — and drafts the PR handoff from that record. |
| Before a human reviews | [corridor-ci](corridor-ci/) | Validates the five-line handoff against the actual diff and appends the recorded evidence to the PR report. |

## Look Ma, no PRs

Full disclosure: I am not a software engineer. I can't write a line of
code, have never reviewed a PR, and have never read a diff line by line.
Check this repo's history — the commits were pushed straight to main by
agents, and the handful of PRs you'll find were opened by agents testing
these tools on themselves. My review process for those: saw green,
pressed merge. Yes, the exact habit this toolkit exists to catch. A pure
vibe coder.

That is exactly why this toolkit exists. I trust the agent's output
unconditionally, because I have no way not to. What's left to doubt is
the process: what actually changed, whether the check actually ran,
whether the next person can actually take over. Every tool here does the
same job — turn "trust me" into a recorded fact. These guardrails aren't
built around the code; they're built around the workflow of someone who
can't read it.

## Install (one command)

```bash
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails ~/guardrails
~/guardrails/install.sh /path/to/your/project
```

Re-running is safe. The installer wires the discipline block (rules plus
the agentcam handoff loop) into `CLAUDE.md` and `AGENTS.md` (Claude Code
reads the former; Codex and friends read the latter), installs the
slime-coding hooks, drops a starter corridor-ci workflow (skipping any
you already have), pip-installs agentcam from the checkout into your
current Python (3.11+ required), and wires agentcam's session hooks so
Claude Code sessions are recorded without the `agentcam run` wrapper.

## The loop

The tools feed each other — that is the point of the package:

1. **Record** — `agentcam run -- <agent command>` (or just work in
   Claude Code: the installer wires agentcam session hooks that record
   automatically). Everything the agent changed is recorded under
   `.git/agentcam/runs/`.
2. **Verify** — `agentcam verify -- pytest -q`. agentcam runs the check
   itself and records command, exit code, and duration — observed facts,
   not the agent's claim. Passing checks draft the handoff's `Verified`
   line.
3. **Hand off** — `agentcam handoff` prints the five-line corridor handoff
   drafted from the record. Paste it into the PR body, then fill in
   `Decision` — the line only the author can know (`Verified` too, if no
   recorded check passed).
4. **Attach evidence** — `agentcam export latest --files .agentcam/`
   writes the redacted run record in committable form; commit it with
   the PR.
5. **Gate** — corridor-ci on the PR validates the handoff against the
   actual diff and appends the recorded evidence (risk flags, recorded
   checks, diff stat) to its report. Evidence is display-only: it informs
   the reviewer, it never flips the check.

Every tool also works standalone — each subdirectory has its own README.

## Versioning

One repo, four tools, so release tags are prefixed per tool:
`agentcam-v0.3.1`, `corridor-ci-v11`, and so on. Earlier releases
(`v0.2.0`, `v10`, …) live in each tool's original repository.

## History

Each tool started as its own repository and was imported here with full
commit history — `git log` inside any subdirectory goes back to that
tool's first commit.

## License

MIT, for the toolkit and for every tool in it.
