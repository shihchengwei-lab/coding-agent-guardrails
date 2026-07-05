# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**CI green is not done. Done is when a human can take over.**

Coding agents finish the task. Tests pass. The check turns green. Then a human
inherits the diff — reads it, owns it, maintains it. Everything the agent left
behind lands on that person's desk.

This repo is four agent-side tools that hold a coding agent to a handoff
standard, at four points between prompt and merge. Each grew out of one working
philosophy:

| Stage | Tool | Philosophy | What it is |
|---|---|---|---|
| Before the agent starts | [kiss-my-diff](kiss-my-diff/) | Occam's razor | A tiny `AGENT.md` rule file: smallest readable change, stop when done. Benchmark: 31% smaller patches, 20% fewer files touched. |
| While the agent works | [slime-coding](slime-coding/) | The slime mold | Claude Code hooks + skills that enforce minimal semantic drift — change only what this task requires, leave architecture and naming alone. |
| After the agent claims done | [agentcam](agentcam/) | Watch what it does, not what it says | A local-first CLI wrapper that records what the agent actually changed and writes a Markdown run report. |
| Before a human reviews | [corridor-ci](corridor-ci/) | First principles: code is cheap, review is not | A GitHub Action that asks every non-trivial PR for a five-line handoff — scope, where to start reading, what was verified — before it earns review attention. |

Each tool works alone. Together they cover the whole corridor from "agent
starts typing" to "human presses merge".

## Quick start

- **kiss-my-diff** — copy [`kiss-my-diff/AGENT.md`](kiss-my-diff/AGENT.md) into
  your repo. That's the entire install.
- **slime-coding** — clone this repo, then
  `./slime-coding/install.sh /path/to/your/project`.
- **agentcam** — `pip install agentcam`
  ([PyPI](https://pypi.org/project/agentcam/)).
- **corridor-ci** — in your workflow:
  `uses: shihchengwei-lab/coding-agent-guardrails/corridor-ci@<tag>`.

Details and docs live in each tool's own README.

## Versioning

One repo, four tools, so release tags are prefixed per tool:
`agentcam-v0.3.0`, `corridor-ci-v11`, and so on. Earlier releases
(`v0.2.0`, `v10`, …) live in each tool's original repository.

## History

Each tool started as its own repository and was imported here with full commit
history — `git log` inside any subdirectory goes back to that tool's first
commit.

## License

MIT, for the collection and for every tool in it.
