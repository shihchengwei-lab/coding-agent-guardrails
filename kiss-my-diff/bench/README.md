# Benchmark

This benchmark compares two prompt variants:

- `baseline`: plain coding-agent prompt.
- `disciplined`: same task prompt, plus `AGENT.md`.

It does not call any model or paid API by itself. It prepares identical task workspaces and scores the finished result.

## Metrics

- `tests`: whether the task tests pass.
- `scope`: whether the agent changed only the expected files and stayed within the file-count limit.
- `simplicity`: whether the patch stayed within the expected diff size.
- `dependencies`: whether the agent avoided dependency changes.
- `quality`: task-specific checks for discipline-relevant behavior, such as reusing an existing helper or preserving an API shape.
- `total`: weighted score, defaulting to 50% tests, 15% scope, 15% simplicity, 10% dependencies, 10% quality. Some discipline-focused tasks put more weight on `quality`.

## Run Protocol

From the repo root:

```powershell
python -m bench.prepare one_line_clamp baseline --force
python -m bench.prepare one_line_clamp disciplined --force
```

Give each run's `PROMPT.md` to the same agent/model, and make it edit only that run's `work` directory:

```text
bench/runs/baseline/one_line_clamp/work
bench/runs/disciplined/one_line_clamp/work
```

After the agent finishes each run:

```powershell
python -m bench.collect bench/runs/baseline/one_line_clamp
python -m bench.collect bench/runs/disciplined/one_line_clamp
python -m bench.score bench/runs/baseline/one_line_clamp/result.json bench/runs/disciplined/one_line_clamp/result.json
```

When results are stored under `bench/runs/<model>/<variant>/<task>/result.json`, summarize by model and variant:

```powershell
python -m bench.report
```

For the natural prompt suite, prepare only `suite=natural` tasks and summarize that run directory:

```powershell
python -m bench.prepare baseline --suite natural --output-dir bench/runs-natural/gpt-5.5 --force
python -m bench.report --runs bench/runs-natural --suite natural
```

The prompt shown to agents intentionally omits scoring guardrails such as allowed files and maximum diff size. Those remain hidden in `bench/tasks.json` and are used only for scoring.

For a fair comparison, keep the model, version, temperature, tool access, and timeout the same. Run each task multiple times per variant if the model is nondeterministic.
