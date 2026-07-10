# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**CI green does not mean the change is complete. Complete means the person
taking over can understand the diff and take responsibility for merging and
maintaining it.**

Coding agents can finish the task, pass the tests, and turn CI green. The hard
part comes next: someone has to take over the diff, understand what changed,
take responsibility for merging it, and maintain it afterward. The model can
produce code, but the person who adopts, merges, and maintains that output is
responsible for it. This toolkit sits on the agent's side before that handoff.
It keeps the handoff facts visible: what changed, which checks ran, and where
the next person starts.

One install connects four tools that cover the path from "agent starts typing"
to "human presses merge". Each tool covers one stage:

| Stage | Tool | What it adds |
|---|---|---|
| Before the agent starts | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) rules | One unified discipline block in your `CLAUDE.md` / `AGENTS.md` ([templates/DISCIPLINE.md](templates/DISCIPLINE.md)): smallest sufficient readable change, minimal semantic drift, stop when done. |
| While the agent works | [slime-coding](slime-coding/) hooks | Automatic gates that hold the agent inside the corridor it declared before editing. |
| After the agent claims done | [agentcam](agentcam/) | Records what actually changed: files, risk flags, diff stat, then drafts the PR handoff from that record. |
| Before a human reviews | [corridor-ci](corridor-ci/) | Validates the five-line handoff against the actual diff and appends the recorded evidence to the PR report. |

The collaboration discipline is one ordered loop, not four interchangeable
slogans: reduce the request to observable necessities (first principles), let
repo evidence support or falsify candidate routes (slime), choose the smallest
sufficient change rather than merely the shortest diff (Occam), then label
manual claims separately from recorded behavior. Read broadly, edit narrowly;
stop when the observable condition is met.

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

The four tools connect into one workflow. That is why they are packaged
together:

1. **Record**: `agentcam run -- <agent command>` (or just work in
   Claude Code: the installer wires agentcam session hooks that record
   automatically). Everything the agent changed is recorded under
   `.git/agentcam/runs/`. Trade-off, disclosed: hook-mode evidence is
   thinner, because Claude Code does not expose terminal output to hooks, so
   output-pattern risk flags (`rm -rf` and friends) are unavailable;
   wrap the session with `agentcam run` when you want the full record.
2. **Verify**: `agentcam verify -- pytest -q`. agentcam runs the check
   itself and records command, exit code, and duration: observed facts,
   not the agent's claim. Passing checks draft the handoff's `Verified`
   line.
3. **Hand off**: `agentcam handoff` prints the five-line corridor handoff
   drafted from the record. Paste it into the PR body, then fill in
   `Decision`, the line only the author can know (`Verified` too, if no
   recorded check passed).
4. **Attach evidence**: `agentcam export latest --files .agentcam/`
   writes the redacted run record in committable form; commit it with
   the PR.
5. **Gate**: corridor-ci on the PR validates the handoff against the
   actual diff and appends the recorded evidence (risk flags, recorded
   checks, diff stat) to its report. It labels verification as recorded,
   manual, or unverified, and marks partial observation. These provenance
   warnings inform the reviewer; they never flip the check.

Every tool also works standalone; each subdirectory has its own README.

## Versioning

One repo, four tools, so release tags are prefixed per tool:
`agentcam-v0.3.3`, `corridor-ci-v11`, and so on. Earlier releases
(`v0.2.0`, `v10`, …) live in each tool's original repository.

## History

Each tool started as its own repository and was imported here with full
commit history. `git log` inside any subdirectory goes back to that
tool's first commit.

## License

MIT, for the toolkit and for every tool in it.
