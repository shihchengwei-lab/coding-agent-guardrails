# Benchmark

This folder contains the small benchmark used by `kiss-my-diff`.

It is intentionally open: the task code, public tests, hidden tests, runner, and scoring code are all checked in. "Hidden" means hidden from the agent workspace during a run, not hidden from readers of this repo.

## Run The Harness

From this folder:

```powershell
python -m pytest -q
python benchmark_runner.py prepare --run-root runs-local --variant baseline --force
python benchmark_runner.py run --run-root runs-local --model gpt-5.5 --variant baseline --task api_response_decode
python benchmark_runner.py collect --run-root runs-local --model gpt-5.5 --variant baseline --task api_response_decode
python benchmark_runner.py summary --run-root runs-local
python benchmark_runner.py calibrate --run-root runs-local
```

Variants:

- `baseline`: no local `AGENT.md`
- `kiss`: copies the repo root `AGENT.md` into the agent workspace
- `kiss_one_line`: uses `Follow the KISS principle (Keep It Simple, Stupid).` See [`one-line-kiss.md`](one-line-kiss.md).
- `kiss_contrast_core`: experimental prompt with positive rules paired with explicit "do not" boundaries
- `kiss_weighted_core`: experimental prompt that repeats the smallest-correct-diff objective before the rule list
- `kiss_weighted_contrast_core`: experimental prompt that combines core weighting with contrast boundaries

The runner creates a fresh worktree under `runs-local/`, gives the agent only `tasks/<task>/base`, then verifies the result twice:

- public tests: restored from `tasks/<task>/base/tests`
- hidden tests: copied from `tasks/<task>/hidden` only during collection

Generated run folders are ignored by git.

`calibrate` checks baseline capability ordering only. It is a sanity check for the task pool, not the main benchmark claim.

See [`context-weighting-experiment.md`](context-weighting-experiment.md) for the extra prompt-strength experiment behind the experimental KISS variants.
