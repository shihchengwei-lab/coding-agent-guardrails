# Smoke benchmark — 2026-06-18

Plan Phase C (§13), reduced. **Purpose: find process gaps, not claim efficacy**
(plan: "smoke benchmark 不用來宣稱有效。它只用來找流程缺口。"). N=1 per cell,
so the only honest output is "preliminary signal".

## What was actually run

- **Conditions:** A `baseline` vs **B `prompt-only` Slime**. *Not* condition C
  (`hooked`): the L2/L3 hooks only intercept the agent inside a hooked Claude
  Code session, which a sub-agent run does not reproduce. The hook *blocking*
  behaviour is verified separately and deterministically by `tests/test.sh`.
  So this smoke tests the **discipline/prompt layer only** (does the Slime
  discipline change what gets written?), not the gates.
- **Tasks:** T1 (small feature `--json`), T4 (abstraction temptation
  `--format text|csv`), T8 (stop-condition `delete <id>`), on `cli-notes`.
- **Agents:** one general-purpose sub-agent per cell, same acceptance criteria,
  differing only in whether the Slime discipline was given. 6 runs total.
- Artifacts per cell: `experiments/runs/2026-06-18/<task>/<cond>/{metrics.json,diff.patch}`.

## Results

All 6 cells: acceptance criteria met (verified by running the CLI), tests pass,
`delete` of a missing id exits non-zero.

| cell | success | tests | product files / lines | tests added | new deps | abstraction | `.slime/` artifact |
|------|:---:|:---:|---|---|:---:|:---:|:---:|
| T1 baseline | ✅ | pass | 1 / +8 −1 | 0 | 0 | none | — |
| T1 prompt-only | ✅ | pass | 1 / +7 −1 | +12 (1 file) | 0 | none | corridor |
| T4 baseline | ✅ | pass | 1 / +15 −1 | 0 | 0 | none (inline branch) | — |
| T4 prompt-only | ✅ | pass | 1 / +10 −1 | 0 | 0 | none (inline branch) | corridor |
| T8 baseline | ✅ | pass | 2 / +22 −1 | 0 | 0 | none | — |
| T8 prompt-only | ✅ | pass | 2 / +21 | +18 (1 file) | 0 | none | corridor |

Over-implementation review (plan §10.3), 0–2: **all six scored 0.**

## Honest reading

1. **Baseline did not over-implement on these tasks.** Even the two temptation
   tasks (T4 abstraction, T8 stop-condition) produced a minimal patch: stdlib
   only, no dependency, no formatter/strategy class, no `--force`/undo/bulk
   gold-plating. The product diff is essentially identical between A and B
   (±2 lines).
2. **Therefore Slime showed no patch-cost reduction here — and a small raw
   increase**, from the `corridor.md` artifact and (T1, T8) extra tests. Per
   anti-hype rule §15.6 this is recorded as-is: on this cell set, prompt-only
   Slime did not produce smaller patches.
3. The extra tests under B are arguably a quality gain, not cost; and the
   `corridor.md` is process overhead, not product. But neither helps H5
   (patch-cost reduction), which is simply not demonstrable when the baseline
   is already minimal.

## The gap this smoke found

The experiment **cannot discriminate** with these tasks: a capable agent does
not bloat small, well-scoped tasks, so there is no baseline excess for Slime to
trim. To test H5 at all, the task set must reliably *elicit* baseline
over-implementation. Candidate fixes before any controlled benchmark:

- Harder / vaguer tasks where "design the whole thing" is tempting (T7-style,
  larger features, an existing messy seam that invites refactor).
- A bigger fixture with real attachment points to ignore/duplicate (T5 parallel
  index, T6 widening).
- A more over-eager agent configuration for the baseline arm (less careful
  system prompt), to model the failure mode Slime targets.
- Measurement: report **product-file** patch cost separately from `.slime/`
  artifacts and added tests, so the comparison is product-to-product.

## Status

- Effect of the discipline layer: **not demonstrated** (and not refuted) — the
  tasks were too easy to tell. No efficacy claim.
- Next: revise the task set for discriminating power, then re-run A vs B (and,
  inside a hooked session, C) on the harder set.
