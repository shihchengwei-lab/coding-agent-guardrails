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

In a calibrated benchmark of 6 bugfix tasks across 4 coding models, the baseline was checked first. It did not show the weak model beating stronger models: `gpt-5.3-codex-spark` scored 83.33 capability, while `gpt-5.4-mini`, `gpt-5.4`, and `gpt-5.5` reached 100.00 on this small suite.

After that sanity check, the same tasks were rerun with `kiss-my-diff`.

| metric | baseline | kiss-my-diff | relative change |
| --- | ---: | ---: | ---: |
| capability score | 95.83 | 100.00 | +4.35% |
| discipline score | 77.26 | 86.23 | +11.62% |
| total score | 90.26 | 95.87 | +6.21% |
| avg changed files | 2.08 | 1.75 | -16.00% |
| avg line delta | 57.75 | 27.08 | -53.10% |

Per-model discipline change:

| model | capability | discipline change | total change | line delta |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.5` | 100.00 -> 100.00 | +10.92% | +2.77% | 35.83 -> 24.00 |
| `gpt-5.4` | 100.00 -> 100.00 | +9.72% | +2.51% | 30.17 -> 26.00 |
| `gpt-5.4-mini` | 100.00 -> 100.00 | +11.08% | +2.66% | 124.33 -> 31.00 |
| `gpt-5.3-codex-spark` | 83.33 -> 100.00 | +14.97% | +18.61% | 40.67 -> 27.33 |

This is still a small single-run benchmark, not a model leaderboard. The useful signal is narrower: once the baseline sanity check is reasonable, this file nudges agents toward smaller, more local patches.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See [`LICENSE`](LICENSE).
