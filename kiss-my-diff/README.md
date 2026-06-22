# kiss-my-diff

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

Agents usually finish the task. The question is whether you want to kiss the diff afterward.

`kiss-my-diff` is a tiny [`AGENT.md`](AGENT.md) for coding agents. It asks the agent to read first, use existing code, make the smallest readable change, verify, and stop.

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

This file is the small reminder: make the diff small enough to love.

## Evidence

First, the benchmark had to pass a sanity check. The weak model did not beat the stronger models:

| baseline only | correctness |
| --- | ---: |
| `gpt-5.5` | 100.00 |
| `gpt-5.4` | 100.00 |
| `gpt-5.4-mini` | 100.00 |
| `gpt-5.3-codex-spark` | 83.33 |

Then the same 6 bugfix tasks were rerun with `kiss-my-diff`.

| what changed | baseline | kiss-my-diff | result |
| --- | ---: | ---: | ---: |
| correctness | 95.83 | 100.00 | +4.35% |
| clean-diff score | 77.26 | 86.23 | +11.62% |
| overall score | 90.26 | 95.87 | +6.21% |
| files touched | 2.08 | 1.75 | 16.00% fewer |
| patch size | 57.75 lines | 27.08 lines | 53.10% smaller |

The useful part is the diff shape: agents touched fewer files and produced much smaller patches.

| model | correctness | clean-diff change | patch size |
| --- | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.92% | 35.83 -> 24.00 lines |
| `gpt-5.4` | 100.00 -> 100.00 | +9.72% | 30.17 -> 26.00 lines |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +11.08% | 124.33 -> 31.00 lines |
| `gpt-5.3-codex-spark` | 83.33 -> 100.00 | +14.97% | 40.67 -> 27.33 lines |

This is still a small single-run benchmark, not a model leaderboard. The narrow claim is simpler: with the same tasks and models, `kiss-my-diff` made the patches smaller and more local.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See [`LICENSE`](LICENSE).
