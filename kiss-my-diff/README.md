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

That is 24.8% smaller patches and 9.8% fewer files touched with unchanged test
correctness in this sample. It is directional evidence, not a general model
claim.

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
