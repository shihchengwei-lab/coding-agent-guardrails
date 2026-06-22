# Natural Prompt Benchmark Report - 2026-06-22

## Scope

This run tests ordinary short prompts, without future-feature bait and without telling the agent to avoid dependencies, avoid refactors, or keep diffs small.

The goal is to measure a more realistic failure mode: code can pass tests while still ignoring existing local helpers or making a larger-than-needed patch.

## Method

- Models: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`.
- Variants:
  - `baseline`: task prompt only.
  - `disciplined`: task prompt plus `AGENT.md`.
- Suite: `natural`.
- Tasks: 6.
- Runs: 48 total, from `4 models x 2 variants x 6 tasks`.
- Raw artifacts: `bench/runs-natural/`.

The generated prompts only included the task and verification command. Hidden scoring rules stayed in `bench/tasks.json`.

## Summary

| model | variant | runs | total avg | pass rate | quality avg | avg line delta | dependency incidents |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | 6 | 85.83 | 100.00 | 33.33 | 6.00 | 0 |
| gpt-5.3-codex-spark | disciplined | 6 | 99.58 | 100.00 | 100.00 | 6.33 | 0 |
| gpt-5.4 | baseline | 6 | 99.58 | 100.00 | 100.00 | 6.17 | 0 |
| gpt-5.4 | disciplined | 6 | 99.58 | 100.00 | 100.00 | 6.17 | 0 |
| gpt-5.4-mini | baseline | 6 | 98.33 | 100.00 | 100.00 | 7.17 | 0 |
| gpt-5.4-mini | disciplined | 6 | 98.96 | 100.00 | 100.00 | 6.67 | 0 |
| gpt-5.5 | baseline | 6 | 98.96 | 100.00 | 100.00 | 6.67 | 0 |
| gpt-5.5 | disciplined | 6 | 99.17 | 100.00 | 100.00 | 6.50 | 0 |

## Non-Perfect Runs

| model | variant | task | total | simplicity | quality | line delta |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | natural_email_search | 80.00 | 100.00 | 0.00 | 3 |
| gpt-5.3-codex-spark | baseline | natural_invoice_cents | 95.00 | 50.00 | 100.00 | 12 |
| gpt-5.3-codex-spark | baseline | natural_module_comments | 80.00 | 100.00 | 0.00 | 6 |
| gpt-5.3-codex-spark | baseline | natural_order_dates | 80.00 | 100.00 | 0.00 | 3 |
| gpt-5.3-codex-spark | baseline | natural_settings_tags | 80.00 | 100.00 | 0.00 | 6 |
| gpt-5.3-codex-spark | disciplined | natural_invoice_cents | 97.50 | 75.00 | 100.00 | 10 |
| gpt-5.4 | baseline | natural_invoice_cents | 97.50 | 75.00 | 100.00 | 10 |
| gpt-5.4 | disciplined | natural_invoice_cents | 97.50 | 75.00 | 100.00 | 10 |
| gpt-5.4-mini | baseline | natural_invoice_cents | 90.00 | 0.00 | 100.00 | 16 |
| gpt-5.4-mini | disciplined | natural_invoice_cents | 93.75 | 37.50 | 100.00 | 13 |
| gpt-5.5 | baseline | natural_invoice_cents | 93.75 | 37.50 | 100.00 | 13 |
| gpt-5.5 | disciplined | natural_invoice_cents | 95.00 | 50.00 | 100.00 | 12 |

## Observations

- Every run passed tests. Correctness alone did not separate the variants.
- No run changed dependencies.
- The strongest signal appeared in `gpt-5.3-codex-spark`: baseline passed tests but missed existing helpers in 4 of 6 tasks, scoring 33.33 quality; disciplined used the helpers and scored 100 quality.
- For larger models, quality stayed 100 in both variants. The remaining difference was smaller patch size on `natural_invoice_cents`.
- The natural prompt suite matches the reported human experience better than the earlier clean suite: it exposes cases where code is functionally correct but locally less integrated.

## Conclusion

The natural-prompt benchmark shows a real but uneven benefit from `AGENT.md`:

- Strong effect for the fastest/smallest coding model: `gpt-5.3-codex-spark` improved from 85.83 to 99.58 total average, mainly by using existing helpers.
- Small patch-size improvement for `gpt-5.4-mini` and `gpt-5.5`.
- No measurable difference for `gpt-5.4` on this suite.

The practical interpretation: discipline instructions matter most when the model is more likely to solve locally from the visible file instead of reading the surrounding repo. For stronger models, the effect is smaller because they already tend to inspect and reuse nearby helper code.
