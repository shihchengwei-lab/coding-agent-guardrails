# Sweet Spot Search - 2026-06-22

## Scope

This run looks for a middle ground between:

- the original longer `AGENT.md`, which performed best but was less minimal;
- the 7-line `AGENT.md`, which was clean but produced mixed benchmark results.

Two 10-line candidates were tested:

## Candidate A: Balanced

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

## Candidate B: Helper-Explicit

```text
Build only what is needed now.
Prefer the smallest readable change.
Read nearby code before editing.
Use existing helpers before writing new logic.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Verify with the smallest relevant test.
Stop when done.
```

Both candidates were run only as `disciplined` variants on the same 18-task `natural` suite. They are compared below against the latest 7-line disciplined run and the earlier longer disciplined run. Because these are single runs, small differences should be treated as noisy.

## Total Score

| model | 7-line disciplined | 10-line balanced | 10-line helper-explicit | longer disciplined |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 97.64 | 98.40 | 97.64 | 98.82 |
| `gpt-5.4` | 99.86 | 98.75 | 98.75 | 99.86 |
| `gpt-5.4-mini` | 97.43 | 99.72 | 100.00 | 98.89 |
| `gpt-5.5` | 98.54 | 98.82 | 98.82 | 100.00 |
| **Average** | **98.37** | **98.92** | **98.80** | **99.39** |

## Quality Score

| model | 7-line disciplined | 10-line balanced | 10-line helper-explicit | longer disciplined |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 88.89 | 100.00 | 88.89 | 100.00 |
| `gpt-5.4` | 100.00 | 94.44 | 94.44 | 100.00 |
| `gpt-5.4-mini` | 88.89 | 100.00 | 100.00 | 94.44 |
| `gpt-5.5` | 94.44 | 94.44 | 94.44 | 100.00 |
| **Average** | **93.05** | **97.22** | **94.44** | **98.61** |

## Patch Size

Average line delta:

| model | 7-line disciplined | 10-line balanced | 10-line helper-explicit | longer disciplined |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.3-codex-spark` | 5.44 | 5.89 | 5.06 | 5.83 |
| `gpt-5.4` | 5.56 | 5.61 | 5.56 | 5.50 |
| `gpt-5.4-mini` | 5.50 | 5.83 | 4.61 | 4.61 |
| `gpt-5.5` | 5.72 | 5.44 | 5.39 | 4.72 |
| **Average** | **5.56** | **5.69** | **5.16** | **5.17** |

## Observations

- The longer `AGENT.md` still has the best overall benchmark profile: highest total average, highest quality average, and strong patch-size behavior.
- The 7-line version is cleaner, but its quality average drops noticeably.
- The 10-line balanced candidate recovers most of the quality benefit while staying much shorter than the longer checklist.
- The helper-explicit candidate gives smaller patches, but it loses quality on `gpt-5.3-codex-spark`, making it less stable as a default.
- The 10-line balanced candidate is the best compromise if the repo wants a short `AGENT.md` that still behaves more like the longer discipline file.

## Recommendation

Use the 10-line balanced candidate as the repo default.

It is not the top-scoring prompt. The longer version still wins on this benchmark. But the balanced version is the better product shape: short enough to be memorable, explicit enough to recover most discipline behavior, and less brittle than the 7-line version.

This benchmark should still not be read as a model leaderboard. It is a discipline-behavior check, and single-run differences can be noisy.
