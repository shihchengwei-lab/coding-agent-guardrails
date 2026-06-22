# Occam Agent

![Occam Agent hero](assets/occam-agent-hero.png)

Agents usually finish the task. The question is how much extra machinery they build on the way.

`Occam Agent` is a tiny repo built around one file: [`AGENT.md`](AGENT.md). It gives coding agents a compact standing instruction set for boring but valuable engineering discipline: build only what is needed, read first, use existing helpers, keep changes local, verify, and stop.

This repo also includes a small benchmark harness that tests the practical claim behind the file:

> `AGENT.md` does not mainly make agents pass tests. It nudges agents to shave off unnecessary abstraction, scope, and ceremony when they already can pass tests.

## Why This Exists

Modern coding agents are often good enough to complete small bugfixes. The pain is usually subtler:

- They pass tests but ignore an existing helper.
- They touch an extra file.
- They add ceremony around a simple fix.
- They solve the local bug with a broader rewrite than needed.
- They choose a clever path when a small patch would do.

`AGENT.md` is meant to bias the agent toward the boring repair.

Think of it as Occam's razor for agentic code edits: cut away the rewrite, the dependency, the future-proof abstraction, and the extra file until the smallest clear fix remains.

## What Is In The Box

- [`AGENT.md`](AGENT.md): the actual standing instruction file.
- [`RESULTS.md`](RESULTS.md): a human-readable summary of the benchmark result.
- [`bench/`](bench/): fixtures, scoring, preparation, collection, reporting, and tests.

The raw benchmark runs are ignored by git so the repo can stay small.

## Benchmark Result

The latest sweet-spot search compared the 7-line file, two 10-line candidates, and the earlier longer checklist:

- 18 ordinary bugfix tasks.
- 4 models.
- 72 runs per candidate version.
- Same hidden scoring for tests, scope, simplicity, dependency changes, and helper reuse.

Every run passed tests. That is the point: pass rate did not show the difference.

| version | avg total | avg quality | avg line delta |
| --- | ---: | ---: | ---: |
| 7-line | 98.37 | 93.05 | 5.56 |
| 10-line balanced | 98.92 | 97.22 | 5.69 |
| 10-line helper-explicit | 98.80 | 94.44 | 5.16 |
| longer original | 99.39 | 98.61 | 5.17 |

The longer version still wins the benchmark. The 10-line balanced version is the current repo default because it recovers most of the quality benefit while staying short enough to be memorable.

Do not read these tables as model leaderboards. The quality score is intentionally discipline-shaped: it rewards using existing helpers and staying local. A stronger model can pass tests with an equivalent inline fix and score lower than a weaker model that happened to reuse the helper.

See [`RESULTS.md`](RESULTS.md) for the short analysis and [`bench/results/2026-06-22-sweet-spot-search.md`](bench/results/2026-06-22-sweet-spot-search.md) for the detailed latest report.

## Use It

Copy [`AGENT.md`](AGENT.md) into a repo where coding agents work.

The file is intentionally short. It is not a framework, policy system, or prompt library. It is a small set of defaults:

- Build only what is needed now.
- Prefer the smallest readable change.
- Read the existing code before editing.
- Use existing helpers and patterns before adding new code.
- Use built-ins before adding dependencies.
- Touch the fewest files needed.
- Do not add abstractions for one-shot code.
- Preserve existing behavior unless asked to change it.
- Verify with the smallest relevant test.
- Stop when done.

## Run The Benchmark

Prepare a suite:

```powershell
python -m bench.prepare baseline --suite natural --output-dir bench/runs-natural-slim/example-model --force
python -m bench.prepare disciplined --suite natural --output-dir bench/runs-natural-slim/example-model --force
```

After agents complete the generated tasks, collect and report:

```powershell
Get-ChildItem bench/runs-natural-slim -Recurse -Filter RUN.json | ForEach-Object {
  python -m bench.collect $_.DirectoryName | Out-Null
}
python -m bench.report --runs bench/runs-natural-slim --suite natural
python -m unittest discover bench/tests
```

## Current Limits

This benchmark is intentionally narrow. It does not yet cover large repos, vague product requests, front-end UI work, database migrations, third-party APIs, or dependency-heavy tasks. It also does not estimate run-to-run variance because each model/variant/task combination was run once.

So the conservative claim is:

> On small natural bugfix tasks, `AGENT.md` does not change whether agents can finish. It changes how locally and simply they tend to finish.

## License

MIT. See [`LICENSE`](LICENSE).
