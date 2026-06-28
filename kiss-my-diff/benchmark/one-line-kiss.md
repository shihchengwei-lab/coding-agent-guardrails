# One-Line KISS Prompt

This benchmark variant uses only:

```text
Follow the KISS principle (Keep It Simple, Stupid).
```

It was run once across the same 8 tasks and 4 models, for 32 runs total.

| variant | runs | correctness | files touched | patch size |
| --- | ---: | ---: | ---: | ---: |
| baseline | 64 | 100.00 | 1.97 | 39.34 lines |
| `kiss-my-diff` | 64 | 96.88 | 1.58 | 27.23 lines |
| one-line KISS | 32 | 93.75 | 1.62 | 24.50 lines |

The one-line prompt made patches shorter than the full rule file in this smaller sample, but correctness was lower. That is why the repo keeps the 11-rule `AGENT.md` as the default.

## Per Model

| model | variant | correctness | files touched | patch size |
| --- | --- | ---: | ---: | ---: |
| `gpt-5.5` | one-line KISS | 87.50 | 1.25 | 16.38 lines |
| `gpt-5.4` | one-line KISS | 100.00 | 1.62 | 24.38 lines |
| `gpt-5.4-mini` | one-line KISS | 100.00 | 1.88 | 26.00 lines |
| `gpt-5.3-codex-spark` | one-line KISS | 87.50 | 1.75 | 31.25 lines |
