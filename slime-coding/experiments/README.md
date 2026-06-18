# Slime Coding — experiments

Harness for validating Slime Coding against the questions in
[`../docs/VALIDATION_PLAN.md`](../docs/VALIDATION_PLAN.md). This directory is
**infrastructure, not results** — running the benchmark and filling in the
numbers is a separate, manual step, and the [anti-hype rules](../docs/VALIDATION_PLAN.md)
(§15) apply: no fabricated metrics, every run keeps its diff, failures recorded.

## Layout

```text
experiments/
├── README.md                 # this file
├── metrics.py                # computes the git-derived metrics for one run
├── schema/metrics.schema.json
├── tasks/T1..T8.md           # frozen task cards (write once, don't cherry-pick)
└── fixtures/                 # small repos with a clean baseline + reset script
    └── cli-notes/
```

Runs are written under a top-level `reports/` and (when produced)
`experiments/runs/<date>/<task>/<condition>/<run>/` per plan §9.

## Conditions (plan §6)

| id | condition | L0 | L1 | L2 | L3 |
|----|-----------|----|----|----|----|
| A | `baseline`      | off | off | off | off |
| B | `prompt-only`   | on  | off | off | off |
| C | `hooked-slime`  | on  | on  | on  | on  |
| D | `hooked-no-l1`  | on  | off | on  | on  |

- **A**: don't install Slime Coding; just give the task prompt.
- **B**: paste `templates/CLAUDE.slime.md` + the skill/commands, no hooks.
- **C**: `./install.sh <fixture>` (full stack).
- **D**: install, then remove the `prune-inject` entries from the project's
  `.claude/settings.json` (SessionStart + UserPromptSubmit).

## Running one cell

Each run uses an **isolated** copy of the fixture as its own git repo (so the
baseline commit and diff don't mix with the slime-coding repo). Use
`slime-bench` (`experiments/slime-bench`) to wrap the building blocks, or
invoke them directly if you prefer:

```bash
# 1. print the matrix (no side-effects) — sanity-check the plan before running
python3 experiments/slime-bench plan T1 \
  --conditions baseline,prompt-only,hooked-slime,hooked-no-l1 --runs 3

# 2. materialize one cell at <root>/<task>/<condition>/run<N> and apply the
#    condition stack (A: nothing; B: skill/commands + CLAUDE.slime.md;
#    C: install.sh full stack; D: C then strip the prune-inject hooks)
ROOT=/tmp/slime-runs/2026-06-18
CELL=$(python3 experiments/slime-bench new-cell \
        --task T1 --condition hooked-slime --run 1 \
        --fixture cli-notes --root "$ROOT" | tail -1)

# 3. write the real corridor (/slime-corridor) and commit it as the task
#    baseline, so later corridor edits show up as a diff:
#    git -C "$CELL" add -A && git -C "$CELL" commit -m corridor

# 4. run the agent on tasks/T1-small-feature.md inside "$CELL", then its tests:
cd "$CELL" && python3 -m unittest -q

# 5. capture the git-derived metrics BEFORE committing the agent's work:
python3 experiments/slime-bench measure "$CELL"          # writes $CELL/metrics.json

# 6. fill in the human-judged fields (task_success, reviewer score, blocks,
#    pruned_path_revived, ...) by hand. Then validate against the schema:
python3 experiments/slime-bench validate "$CELL/metrics.json"

# 7. once a batch is done, aggregate the runs root into a markdown table:
python3 experiments/slime-bench aggregate "$ROOT"
```

`measure` only fills the deterministic columns (plan §10.2); the judged
columns are emitted as `null` on purpose so nobody invents them. `validate`
fails on a raw `measure` output — that is the design: the runner refuses to
treat un-judged runs as complete, so the human-judged columns can't be
silently skipped.

`experiments/fixtures/<name>/reset.sh` resets the **in-repo** fixture source if
you edited it in place (the isolated run repos are just thrown away).

## Status

- **Mechanism layer (plan Q1/Q2/Q3, §11 "機制驗證成功")**: covered by
  `tests/test.sh` + CI. See [`../reports/`](../reports/) for the mechanism
  verification note.
- **Effect layer (plan Q4/Q5)**: two A-vs-B smoke runs exist.
  - [`../reports/2026-06-18-smoke-report.md`](../reports/2026-06-18-smoke-report.md)
    (runs under `runs/2026-06-18/`): the first task set could not discriminate.
  - [`../reports/2026-06-18-discriminating-smoke.md`](../reports/2026-06-18-discriminating-smoke.md)
    (runs under `runs/2026-06-18-discriminating/`): tasks baited to elicit
    over-implementation. One axis (speculative extensibility) discriminated —
    baseline built a format registry the Slime arm pruned. A signal, N=1.
  - [`../reports/2026-06-18-extensibility-3runs.md`](../reports/2026-06-18-extensibility-3runs.md)
    (runs under `runs/2026-06-18-extensibility/`): the extensibility axis on 3
    tasks × 3 runs. Reproduces — baseline built a speculative
    registry/abstraction 9/9, Slime 1/9; ~50–60% less product code at equal
    functionality. Narrow (one axis, prompt-only, one fixture); **still no
    general efficacy claim**.
  - [`../reports/2026-06-18-js-wording.md`](../reports/2026-06-18-js-wording.md)
    (runs under `runs/2026-06-18-js-wording/`): second language (`js-notes`) +
    wording variation. The effect is **not** a language or exact-phrase artifact
    (JS reproduces it; "make it extensible" also triggers it), but it is
    **conditional on an extensibility hint** — with no hint, baseline and Slime
    both stay minimal. Sharpens the claim: Slime resists an *explicit invitation*
    to over-build, not over-implementation in general.
  - [`../reports/2026-06-18-condition-c.md`](../reports/2026-06-18-condition-c.md)
    (runs under `runs/2026-06-18-condition-c/`): the L2 dependency gate on the
    `dart-mini-app` fixture. Disciplined agents didn't add a dependency (gate
    silent); when an agent over-reaches, the real gate blocks and the block
    drives removal. The gate is a backstop, not an extra reducer — not an
    automated hooked run (sub-agents can't trigger the harness hooks).
