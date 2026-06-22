# Subagent Benchmark Report - 2026-06-22

## Scope

This benchmark compares two prompt variants in Codex subagents:

- `baseline`: task prompt only.
- `disciplined`: task prompt plus `AGENT.md`.

This is not a raw-model benchmark. All runs still happen inside the Codex agent environment, so the baseline is already somewhat disciplined by the surrounding system behavior.

## Method

- Models: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`.
- Tasks: 8 tasks from `bench/tasks.json`.
- Runs: 64 total, from `4 models x 2 variants x 8 tasks`.
- Scoring dimensions: tests, scope, simplicity, dependencies, quality.
- Hidden scoring guardrails were not shown in generated `PROMPT.md` files.
- Raw run artifacts are under `bench/runs/` and are ignored by Git.

## Summary

| model | variant | runs | total avg | pass rate | quality avg | avg line delta | dependency incidents |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | 8 | 100.00 | 100.00 | 100.00 | 4.88 | 0 |
| gpt-5.3-codex-spark | disciplined | 8 | 100.00 | 100.00 | 100.00 | 4.62 | 0 |
| gpt-5.4 | baseline | 8 | 99.84 | 100.00 | 100.00 | 4.25 | 0 |
| gpt-5.4 | disciplined | 8 | 100.00 | 100.00 | 100.00 | 3.75 | 0 |
| gpt-5.4-mini | baseline | 8 | 99.84 | 100.00 | 100.00 | 4.25 | 0 |
| gpt-5.4-mini | disciplined | 8 | 99.84 | 100.00 | 100.00 | 4.00 | 0 |
| gpt-5.5 | baseline | 8 | 100.00 | 100.00 | 100.00 | 4.62 | 0 |
| gpt-5.5 | disciplined | 8 | 100.00 | 100.00 | 100.00 | 3.88 | 0 |

## Non-Perfect Runs

Only three runs scored below 100, all on `money_rounding`, all due to patch size:

| model | variant | task | total | simplicity | line delta |
| --- | --- | --- | ---: | ---: | ---: |
| gpt-5.4 | baseline | money_rounding | 98.75 | 87.50 | 9 |
| gpt-5.4-mini | baseline | money_rounding | 98.75 | 87.50 | 9 |
| gpt-5.4-mini | disciplined | money_rounding | 98.75 | 87.50 | 9 |

## Observations

- Test pass rate did not separate the variants: every run passed tests.
- Quality checks did not separate the variants: every run scored 100 on quality.
- Dependency behavior did not separate the variants: no run changed dependencies.
- The only measurable signal was patch size. The disciplined variant had a lower average line delta for every model except `gpt-5.4-mini`, where total score stayed equal and line delta was still slightly lower.

## Conclusion

The current benchmark does not show a large correctness or quality gap between `baseline` and `disciplined` prompts. In this Codex subagent setting, the strongest measurable effect is modestly smaller patches with the disciplined prompt:

- `gpt-5.3-codex-spark`: average line delta improved from 4.88 to 4.62.
- `gpt-5.4`: average line delta improved from 4.25 to 3.75, and total average improved from 99.84 to 100.00.
- `gpt-5.4-mini`: average line delta improved from 4.25 to 4.00, with equal total average.
- `gpt-5.5`: average line delta improved from 4.62 to 3.88.

The practical reading is conservative: `AGENT.md` did not improve pass rate on these tasks because baseline was already strong, but it appears to nudge solutions toward smaller diffs. To get a stronger benchmark, the next task set needs harder traps: incomplete tests, multi-file distractors, tempting dependency notes, existing helpers that are easy to miss, and scoring that rewards minimal API-preserving fixes.
