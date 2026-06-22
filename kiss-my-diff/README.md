# Occam Agent

![Occam Agent hero](assets/occam-agent-hero.png)

Agents usually finish the task. The question is how much extra machinery they build on the way.

`Occam Agent` is a tiny [`AGENT.md`](AGENT.md) for coding agents. It asks the agent to read first, use existing code, make the smallest readable change, verify, and stop.

## The File

```text
Build only what is needed now.
Prefer the smallest readable change.
Read the existing code before editing.
Use existing helpers and patterns before adding new code.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Verify with the smallest relevant test.
Stop when done.
```

## Why

Modern coding agents can usually make tests pass. The common failure mode is overbuilding: extra files, new abstractions, duplicated helper logic, broader rewrites, or dependencies that were not needed.

This file is the small reminder: shave off unnecessary abstraction, scope, and ceremony.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See [`LICENSE`](LICENSE).
