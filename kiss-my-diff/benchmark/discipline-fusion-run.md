# Fused Discipline Block (2026-07-05 Run)

This benchmark variant used the toolkit discipline text as it existed on
2026-07-05. That historical measured fixture is committed verbatim as
[`fixtures/discipline-fusion-20260705.md`](fixtures/discipline-fusion-20260705.md)
so later edits to the live [`templates/DISCIPLINE.md`](../../templates/DISCIPLINE.md)
cannot silently inherit these results.

Measured discipline SHA-256:
`sha256:e218bba510a9cf078cf55e6eff8e96171d2483c3144b4cad742618947dfc3f2b`.

Committed 32-row scoring input SHA-256:
`sha256:4c8c2f7bb2097386e179042085b2a7bd1b04760d1e6f52b56e74fde2bb1be45d`.

Two arms, run the same day on the same model snapshot: `gpt-5.5` via the
Codex CLI, 8 tasks × 2 repetitions per arm (32 runs). The historical
tables recorded in `one-line-kiss.md` and `context-weighting-experiment.md`
were measured months earlier on different model snapshots, so they are
not a valid control group for these runs; only the same-day baseline is.

| variant | runs | correctness | files touched | patch size |
| --- | ---: | ---: | ---: | ---: |
| baseline | 16 | 100.00 | 1.94 | 35.31 lines |
| fused discipline | 16 | 100.00 | 1.75 | 26.56 lines |

The fused block kept correctness at 100.00 (public and hidden tests, all
32 runs) while producing 24.8% smaller patches and touching 9.8% fewer
files than the same-day baseline. The harness's discipline score moved
from 78.94 to 86.42.

## Method Notes

- The historical measured fixture was the shipped block at run time. It
  references slime-coding hooks and
  agentcam commands that do not exist in the benchmark workspace, so this
  measures the text as plain prompt pressure — the same condition every
  other variant is measured under — not the full hook system.
- Per-run budget is the harness default (600 s). One run
  (`r1/baseline/markdown_heading_links`) hit the budget and was retried
  once on a freshly re-prepared workspace; the retry finished in under 4
  minutes. No other run was retried.
- Raw model output and work folders remain local (`runs-fusion-20260705/`,
  gitignored). The 32 `result.json` scoring records are committed as one array
  in [`results/discipline-fusion-20260705/result.json`](results/discipline-fusion-20260705/result.json),
  and the runner-recomputed output is
  [`results/discipline-fusion-20260705/summary.md`](results/discipline-fusion-20260705/summary.md).
  A fresh clone can recompute the table with:

  ```bash
  python benchmark_runner.py summary --run-root results/discipline-fusion-20260705
  ```

## Limits

One model, one day, 16 runs per arm. Directional, not proof — the same
reading discipline the other snapshots in this lab ask for.
