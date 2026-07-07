# Discipline fusion run — machine-generated summary

This is the verbatim output of `benchmark_runner.py summary` for the
discipline-fusion run described in
[`discipline-fusion-run.md`](discipline-fusion-run.md): `gpt-5.5`,
baseline vs the fused `templates/DISCIPLINE.md` block, 8 tasks × 2
repetitions = 16 runs per arm.

It is committed as the machine-generated backing for the discipline
scores that doc reports (baseline 78.94 → fused 86.42). The raw per-run
folders (`runs-fusion-20260705/`) stay gitignored and local-only — this
aggregate is the reproducible artifact from them. The headline
64-run tables in the main `README.md` were measured earlier on model
snapshots that have since moved on, and have no committed backing.

Regenerate with:

```bash
python benchmark_runner.py summary --run-root runs-fusion-20260705
```

| model | variant | runs | capability | discipline | total |
| --- | --- | ---: | ---: | ---: | ---: |
| gpt-5.5 | baseline | 16 | 100.00 | 78.94 | 93.68 |
| gpt-5.5 | discipline | 16 | 100.00 | 86.42 | 95.93 |
