# Discipline fusion run — machine-generated summary

The table below is the verbatim output of `benchmark_runner.py summary` for
the discipline-fusion run described in
[`discipline-fusion-run.md`](discipline-fusion-run.md): `gpt-5.5`,
baseline vs the historical measured fixture
[`fixtures/discipline-fusion-20260705.md`](fixtures/discipline-fusion-20260705.md),
8 tasks × 2
repetitions = 16 runs per arm.

Measured discipline SHA-256:
`sha256:e218bba510a9cf078cf55e6eff8e96171d2483c3144b4cad742618947dfc3f2b`.

It is committed as the machine-generated backing for the discipline
scores that doc reports (baseline 78.94 → fused 86.42). The raw per-run
folders (`runs-fusion-20260705/`) stay gitignored and local-only — this
aggregate and immutable prompt fixture preserve what was measured, but a fresh
clone cannot recompute the aggregate without those raw folders. The headline
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
