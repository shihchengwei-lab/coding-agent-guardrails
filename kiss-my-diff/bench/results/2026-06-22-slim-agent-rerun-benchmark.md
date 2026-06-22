# Slim Agent Benchmark Rerun - 2026-06-22

## Scope

This rerun uses the simplified 7-line `AGENT.md`:

```text
Build only what is needed now.
Prefer the smallest readable change.
Touch the fewest files needed.
Use existing code before adding new code.
Do not add abstractions for one-shot code.
Verify the result.
Stop when done.
```

The benchmark keeps the same expanded `natural` suite as the previous report:

- 18 ordinary bugfix tasks.
- 4 models.
- 2 variants: baseline prompt vs. prompt plus `AGENT.md`.
- 144 total runs.
- No future-feature bait.
- No instruction to avoid dependencies.
- No instruction to avoid refactors.
- No exposed scoring guardrails.

Raw artifacts are stored under `bench/runs-natural-slim/` and are ignored by git.

## Summary

| model | variant | runs | total avg | pass rate | quality avg | avg line delta | dependency incidents |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | 18 | 98.82 | 100.00 | 94.44 | 5.28 | 0 |
| gpt-5.3-codex-spark | disciplined | 18 | 97.64 | 100.00 | 88.89 | 5.44 | 0 |
| gpt-5.4 | baseline | 18 | 93.19 | 100.00 | 66.67 | 5.17 | 0 |
| gpt-5.4 | disciplined | 18 | 99.86 | 100.00 | 100.00 | 5.56 | 0 |
| gpt-5.4-mini | baseline | 18 | 97.85 | 100.00 | 94.44 | 6.06 | 0 |
| gpt-5.4-mini | disciplined | 18 | 97.43 | 100.00 | 88.89 | 5.50 | 0 |
| gpt-5.5 | baseline | 18 | 98.82 | 100.00 | 94.44 | 5.50 | 0 |
| gpt-5.5 | disciplined | 18 | 98.54 | 100.00 | 94.44 | 5.72 | 0 |

## Deltas

Positive total and quality deltas favor `disciplined`. Negative line delta change means `disciplined` used a smaller average patch.

| model | total delta | quality delta | line delta change |
| --- | ---: | ---: | ---: |
| gpt-5.3-codex-spark | -1.18 | -5.56 | +0.17 |
| gpt-5.4 | +6.67 | +33.33 | +0.39 |
| gpt-5.4-mini | -0.42 | -5.56 | -0.56 |
| gpt-5.5 | -0.28 | +0.00 | +0.22 |

## Non-Perfect Runs

| model | variant | task | total | scope | simplicity | quality | line delta |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| gpt-5.3-codex-spark | baseline | natural_invoice_cents | 98.75 | 100.00 | 87.50 | 100.00 | 9 |
| gpt-5.3-codex-spark | baseline | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.3-codex-spark | disciplined | natural_coupon_case | 80.00 | 100.00 | 100.00 | 0.00 | 2 |
| gpt-5.3-codex-spark | disciplined | natural_invoice_cents | 97.50 | 100.00 | 75.00 | 100.00 | 10 |
| gpt-5.3-codex-spark | disciplined | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.4 | baseline | natural_coupon_case | 80.00 | 100.00 | 100.00 | 0.00 | 2 |
| gpt-5.4 | baseline | natural_invoice_cents | 97.50 | 100.00 | 75.00 | 100.00 | 10 |
| gpt-5.4 | baseline | natural_locale_price | 80.00 | 100.00 | 100.00 | 0.00 | 2 |
| gpt-5.4 | baseline | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.4 | baseline | natural_module_comments | 80.00 | 100.00 | 100.00 | 0.00 | 7 |
| gpt-5.4 | baseline | natural_order_dates | 80.00 | 100.00 | 100.00 | 0.00 | 2 |
| gpt-5.4 | baseline | natural_settings_tags | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.4 | disciplined | natural_invoice_cents | 97.50 | 100.00 | 75.00 | 100.00 | 10 |
| gpt-5.4-mini | baseline | natural_invoice_cents | 76.25 | 100.00 | 62.50 | 0.00 | 11 |
| gpt-5.4-mini | baseline | natural_settings_tags | 85.00 | 25.00 | 100.00 | 100.00 | 7 |
| gpt-5.4-mini | disciplined | natural_coupon_case | 80.00 | 100.00 | 100.00 | 0.00 | 2 |
| gpt-5.4-mini | disciplined | natural_invoice_cents | 93.75 | 100.00 | 37.50 | 100.00 | 13 |
| gpt-5.4-mini | disciplined | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.5 | baseline | natural_invoice_cents | 98.75 | 100.00 | 87.50 | 100.00 | 9 |
| gpt-5.5 | baseline | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.5 | disciplined | natural_invoice_cents | 95.00 | 100.00 | 50.00 | 100.00 | 12 |
| gpt-5.5 | disciplined | natural_markdown_title | 80.00 | 100.00 | 100.00 | 0.00 | 5 |
| gpt-5.5 | disciplined | natural_permission_alias | 98.75 | 100.00 | 87.50 | 100.00 | 9 |

## Observations

- Every run passed tests. As before, pass rate does not expose the relevant difference.
- No run changed dependencies. This suite still does not reproduce dependency bloat.
- Do not read the absolute score table as a model-strength ranking. The benchmark uses binary quality checks for discipline behaviors such as helper reuse, so a model can pass tests with an equivalent inline implementation and still receive `quality = 0`.
- The 7-line `AGENT.md` produced mixed results rather than a uniform win.
- `gpt-5.4` showed a strong discipline benefit: total average improved from 93.19 to 99.86, and quality improved from 66.67 to 100.00.
- `gpt-5.3-codex-spark`, `gpt-5.4-mini`, and `gpt-5.5` did not improve on total score in this single rerun.
- `gpt-5.4-mini` did produce a smaller average patch under `disciplined`, but lost quality on two tasks.
- The fresh baselines differ from the previous report, so this suite still needs repeated runs before treating small deltas as stable.

Example: in `natural_coupon_case`, `gpt-5.4` baseline used `code.strip().upper()` inline, while `gpt-5.3-codex-spark` baseline called the existing `normalize_code()` helper. Both passed tests, but only the helper-reuse solution passed the hidden quality check. That explains why a weaker/faster model can score higher than a stronger model in this benchmark.

## Conclusion

The simplified 7-line `AGENT.md` preserves the core positioning but weakens the measured claim:

`AGENT.md` still does not affect whether agents can complete these small bugfix tasks. All variants passed all tests. Its effect on coding discipline is now model-dependent and noisy: strongly positive for `gpt-5.4`, neutral or slightly negative for the other three models in this single rerun.

The conservative conclusion is that the tiny file is directionally useful as a low-cost discipline nudge, but this benchmark no longer supports saying it is consistently beneficial across all tested models. It also should not be used to rank model capability across models without repeated runs and a less binary quality rubric.
