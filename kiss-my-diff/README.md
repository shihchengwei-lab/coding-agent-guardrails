# kiss-my-diff

![kiss-my-diff hero](assets/kiss-my-diff-hero.png)

`kiss-my-diff` is a small [`AGENT.md`](AGENT.md) for coding agents: read the
repository first, reuse what exists, make the smallest readable change that
solves the task, verify it, and stop.

In this monorepo the active rules ship through the root installer as part of
[`templates/DISCIPLINE.md`](../templates/DISCIPLINE.md). `AGENT.md` remains
unchanged as the standalone measured specimen.

## The file

```text
Build only what is needed now.
Prefer the smallest readable change.
Read the existing code before editing.
Use existing helpers and patterns before adding new code.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Do not hide errors or invalid states.
Verify with the smallest relevant test.
Stop when done.
```

## Reproducible measurement

The maintained result is a same-day two-arm run of the fused discipline text:
8 tasks × 2 repetitions, baseline and discipline, on one `gpt-5.5` snapshot.

| variant | runs | correctness | files touched | patch size |
|---|---:|---:|---:|---:|
| baseline | 16 | 100.00 | 1.94 | 35.31 lines |
| fused discipline | 16 | 100.00 | 1.75 | 26.56 lines |

That is 24.8% smaller patches and 9.7% fewer files touched (31 → 28 files,
565 → 425 lines over 16 runs per arm) with unchanged test correctness in this
sample. It is directional evidence, not a general model claim.

Two honest caveats about what that delta measures. First, a substantial part
of the line reduction is **suppressed test writing**: every task budgets
`max_files: 1`, the harness discards agent-written tests before verification
but still counts them against the file/line budgets, and 15/16 baseline runs
touched a `tests/` file versus 12/16 discipline runs. The discipline gain is
partly a trade-off (fewer regression tests written), not purely bloat
reduction. Second, correctness is saturated at 100% in both arms, so this
sample has no power to detect a correctness cost of the prompt — "unchanged
correctness" here means "not observed to regress", not "shown safe".

The exact prompt fixture, 32 scoring records, their SHA-256 hashes, method notes,
and recomputation command are committed in
[`benchmark/discipline-fusion-run.md`](benchmark/discipline-fusion-run.md).
The task code, public tests, hidden tests, scorer, and runner are also checked in.
Raw model transcripts are not; the committed scoring inputs are sufficient to
recompute the published aggregate, not to replay the model calls.

## Use

Copy [`AGENT.md`](AGENT.md) into a repository, or use the monorepo root
installer to install the full discipline and guardrail loop.

## License

MIT
