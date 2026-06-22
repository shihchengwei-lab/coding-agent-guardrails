# Natural Prompt Benchmark Report v2 - 2026-06-22

## Scope

This benchmark expands the `natural` suite from 6 tasks to 18 tasks. Prompts are ordinary short bug reports:

- No future-feature bait.
- No instruction to avoid dependencies.
- No instruction to avoid refactors.
- No exposed scoring guardrails.

The goal is to test whether `AGENT.md` changes everyday coding behavior when code can pass tests but still ignore existing repo helpers, touch extra files, or make larger patches.

## Method

- Models: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`.
- Variants:
  - `baseline`: task prompt only.
  - `disciplined`: task prompt plus `AGENT.md`.
- Suite: `natural`.
- Tasks: 18.
- Runs: 144 total, from `4 models x 2 variants x 18 tasks`.
- Raw artifacts: `bench/runs-natural-v2/`.

## Summary

| model | variant | runs | total avg | pass rate | quality avg | avg line delta | dependency incidents |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | 18 | 92.92 | 100.00 | 72.22 | 6.06 | 0 |
| gpt-5.3-codex-spark | disciplined | 18 | 98.82 | 100.00 | 100.00 | 5.83 | 0 |
| gpt-5.4 | baseline | 18 | 100.00 | 100.00 | 100.00 | 5.44 | 0 |
| gpt-5.4 | disciplined | 18 | 99.86 | 100.00 | 100.00 | 5.50 | 0 |
| gpt-5.4-mini | baseline | 18 | 96.74 | 100.00 | 88.89 | 5.83 | 0 |
| gpt-5.4-mini | disciplined | 18 | 98.89 | 100.00 | 94.44 | 4.61 | 0 |
| gpt-5.5 | baseline | 18 | 99.93 | 100.00 | 100.00 | 5.50 | 0 |
| gpt-5.5 | disciplined | 18 | 100.00 | 100.00 | 100.00 | 4.72 | 0 |

## Deltas

| model | total delta | quality delta | line delta change |
| --- | ---: | ---: | ---: |
| gpt-5.3-codex-spark | +5.90 | +27.78 | -0.23 |
| gpt-5.4 | -0.14 | +0.00 | +0.06 |
| gpt-5.4-mini | +2.15 | +5.55 | -1.22 |
| gpt-5.5 | +0.07 | +0.00 | -0.78 |

Positive total and quality deltas favor `disciplined`. Negative line delta change means `disciplined` used a smaller average patch.

## Non-Perfect Runs

| model | variant | task | total | scope | simplicity | quality | line delta | changed files |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | natural_coupon_case | 80.00 | 100.00 | 100.00 | 0.00 | 3 | 1 |
| gpt-5.3-codex-spark | baseline | natural_invoice_cents | 97.50 | 100.00 | 75.00 | 100.00 | 10 | 1 |
| gpt-5.3-codex-spark | baseline | natural_locale_price | 80.00 | 100.00 | 100.00 | 0.00 | 3 | 1 |
| gpt-5.3-codex-spark | baseline | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 | 1 |
| gpt-5.3-codex-spark | baseline | natural_module_comments | 80.00 | 100.00 | 100.00 | 0.00 | 8 | 1 |
| gpt-5.3-codex-spark | baseline | natural_settings_tags | 80.00 | 100.00 | 100.00 | 0.00 | 5 | 1 |
| gpt-5.3-codex-spark | baseline | natural_temperature_units | 75.00 | 25.00 | 0.00 | 100.00 | 16 | 2 |
| gpt-5.3-codex-spark | disciplined | natural_invoice_cents | 96.25 | 100.00 | 62.50 | 100.00 | 11 | 1 |
| gpt-5.3-codex-spark | disciplined | natural_temperature_units | 82.50 | 25.00 | 75.00 | 100.00 | 10 | 2 |
| gpt-5.4 | disciplined | natural_invoice_cents | 97.50 | 100.00 | 75.00 | 100.00 | 10 | 1 |
| gpt-5.4-mini | baseline | natural_invoice_cents | 76.25 | 100.00 | 62.50 | 0.00 | 11 | 1 |
| gpt-5.4-mini | baseline | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 | 1 |
| gpt-5.4-mini | baseline | natural_temperature_units | 85.00 | 25.00 | 100.00 | 100.00 | 7 | 2 |
| gpt-5.4-mini | disciplined | natural_invoice_cents | 80.00 | 100.00 | 100.00 | 0.00 | 6 | 1 |
| gpt-5.5 | baseline | natural_invoice_cents | 98.75 | 100.00 | 87.50 | 100.00 | 9 | 1 |

## Observations

- Every run passed tests. Test pass rate alone still hides the relevant differences.
- No run changed dependencies. Dependency bloat did not appear in this suite.
- `gpt-5.3-codex-spark` showed a large discipline benefit: baseline passed tests but missed helper-use quality checks in 5 tasks and changed an extra file in 1 task; disciplined restored quality to 100.
- `gpt-5.4-mini` also benefited: total average improved from 96.74 to 98.89, quality improved from 88.89 to 94.44, and average patch size dropped from 5.83 to 4.61.
- `gpt-5.5` was already strong, but disciplined still reduced average patch size and recovered the small total gap.
- `gpt-5.4` was an outlier: baseline hit 100 and disciplined lost a small simplicity point on `natural_invoice_cents`.

## Conclusion

The expanded natural-prompt suite supports a more precise conclusion:

`AGENT.md` does not mainly improve test pass rate on these tasks, because all variants pass tests. Its measurable value is in local code discipline: using existing helpers, staying within the expected file boundary, and sometimes producing smaller patches.

The effect is strongest for weaker or faster models. Stronger models already behave more like disciplined agents on this suite, so the marginal benefit is smaller and sometimes lost in single-run noise.
