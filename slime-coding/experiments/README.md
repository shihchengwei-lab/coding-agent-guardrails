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
baseline commit and diff don't mix with the slime-coding repo).

```bash
# 1. materialize the fixture as a standalone repo with a baseline commit
RUN=/tmp/slime-run/T1-C-1
experiments/new-run.sh cli-notes "$RUN"

# 2. set up the condition (A: skip; B: paste CLAUDE.slime.md + skill/commands;
#    C: install full stack; D: install then remove prune-inject hooks)
./install.sh "$RUN"                       # condition C

# 3. write the real corridor (/slime-corridor) and commit it as the task
#    baseline, so later corridor edits show up as a diff:
#    git -C "$RUN" add -A && git -C "$RUN" commit -m corridor

# 4. run the agent on tasks/T1-small-feature.md inside "$RUN", then its tests:
cd "$RUN" && python3 -m unittest -q

# 5. capture the git-derived metrics BEFORE committing the agent's work:
python3 experiments/metrics.py --repo "$RUN" \
  --task T1 --condition hooked-slime --run 1 > "$RUN/metrics.json"

# 6. fill in the human-judged fields (task_success, reviewer score, blocks,
#    pruned_path_revived, ...) by hand, validate against the schema, and save
#    the run folder (prompt, diff.patch, stop-report, metrics.json, notes).
```

`metrics.py` only fills the deterministic columns (plan §10.2); the judged
columns are emitted as `null` on purpose so nobody invents them.

`experiments/fixtures/<name>/reset.sh` resets the **in-repo** fixture source if
you edited it in place (the isolated run repos are just thrown away).

## Status

- **Mechanism layer (plan Q1/Q2/Q3, §11 "機制驗證成功")**: covered by
  `tests/test.sh` + CI. See [`../reports/`](../reports/) for the mechanism
  verification note.
- **Effect layer (plan Q4/Q5)**: a first A-vs-B smoke run exists
  ([`../reports/2026-06-18-smoke-report.md`](../reports/2026-06-18-smoke-report.md),
  artifacts under `runs/2026-06-18/`). It found the task set cannot yet
  discriminate (baseline did not over-implement on these small tasks), so **no
  efficacy is claimed**. The controlled benchmark needs a discriminating task
  set first.
