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

In an internal benchmark of 18 small bugfix tasks across 4 coding models, every run passed tests. The difference showed up in discipline checks: using existing helpers, staying local, and avoiding unnecessary code.

| metric | baseline | kiss-my-diff | relative change |
| --- | ---: | ---: | ---: |
| pass rate | 100.00 | 100.00 | +0.00% |
| total score | 97.17 | 98.92 | +1.80% |
| quality score | 87.50 | 97.22 | +11.11% |
| avg line delta | 5.50 | 5.69 | +3.45% |
| dependency incidents | 0 | 0 | 0 |

Per-model breakdown:

| model | total score | total change | quality score | quality change | avg line delta | line delta change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 98.82 -> 98.40 | -0.43% | 94.44 -> 100.00 | +5.89% | 5.28 -> 5.89 | +11.55% |
| `gpt-5.4` | 93.19 -> 98.75 | +5.97% | 66.67 -> 94.44 | +41.65% | 5.17 -> 5.61 | +8.51% |
| `gpt-5.4-mini` | 97.85 -> 99.72 | +1.91% | 94.44 -> 100.00 | +5.89% | 6.06 -> 5.83 | -3.80% |
| `gpt-5.5` | 98.82 -> 98.82 | +0.00% | 94.44 -> 94.44 | +0.00% | 5.50 -> 5.44 | -1.09% |

Relative change is computed against the baseline. For avg line delta, negative means a smaller patch. This is not a model leaderboard. It is a small discipline benchmark, and single-run differences are noisy. The useful signal is narrower: when agents already pass tests, this file nudges them toward existing code and local fixes.

## Use

Copy [`AGENT.md`](AGENT.md) into the root of a repo where coding agents work.

## License

MIT. See [`LICENSE`](LICENSE).
