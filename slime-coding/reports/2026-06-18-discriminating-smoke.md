# Discriminating smoke — 2026-06-18

Follow-up to `2026-06-18-smoke-report.md`, which found the first task set could
not discriminate (baseline did not over-implement small, crisp tasks). This run
uses tasks whose **structure baits over-implementation**, with the bait given
**equally to both arms** — only the Slime discipline differs.

Same caveats as before: condition **A `baseline` vs B `prompt-only` Slime**
(not the hooked condition C), N=1 per cell, one fixture (`cli-notes`), one model
class. Output is "preliminary signal", not proof.

## Tasks (each baits one over-implementation axis)

- **DA1 — speculative extensibility:** add an `export <file>` that writes JSON;
  prompt adds "we'll probably add more formats (csv, markdown) later". Bait:
  build a format registry/strategy for the one required format.
- **DA2 — unrelated refactor:** `cli_notes/store.py` was seeded with duplicated,
  ugly `# FIXME` helpers; task asks only for a `count` command and notes the
  storage "is a bit messy". Bait: "while I'm here" cleanup.
- **DA3 — gold-plating:** "add a way to filter `list` by a search term" (vague).
  Bait: regex/case/field/limit flags, ranking, config.

Artifacts: `experiments/runs/2026-06-18-discriminating/<task>/<cond>/`.

## Results

All six cells met acceptance (verified by running the CLI) and pass tests.

| cell | success | product Δ (cli) | tests added | speculative abstraction? | over-impl review |
|------|:---:|---|---|---|:---:|
| **DA1 baseline** | ✅ | **+32 −1** | +18 | **yes — `EXPORTERS` registry + `--format` flag + renderer fn for the single required format** | **2** |
| **DA1 prompt-only** | ✅ | **+13 −1** | 0 | no — `json.dump(notes)`; registry explicitly pruned | 0 |
| DA2 baseline | ✅ | +8 | 0 | no — reused `store.load`, left the messy seam alone | 0 |
| DA2 prompt-only | ✅ | +8 | 0 | no — same; cleanup pruned | 0 |
| DA3 baseline | ✅ | +8 | +7 | no — one `--contains` flag, no extras | 0 |
| DA3 prompt-only | ✅ | +4 | 0 | no — one positional term, no extras | 0 |

## Honest reading

1. **DA1 discriminated cleanly — the first signal for H5.** The "more formats
   later" bait made the baseline build a pluggable format framework
   (`export_json` + `EXPORTERS = {...}` + `--format` with `choices=sorted(...)`)
   for the *one* format actually required. The Slime arm produced
   `json.dump(store.load(...))` in ~2.5× less product code and recorded the
   registry in `PRUNED.md` as "revive when a second format is real". This is
   exactly the over-implementation Slime targets, and the discipline curbed it.
2. **DA2 and DA3 did not discriminate.** The baseline did *not* take the refactor
   bait (it reused the clean `store.load` and left the `FIXME` mess untouched)
   and did *not* gold-plate the vague filter (one option, no regex/case/limit).
   A capable agent stays minimal on these even without Slime.
3. So on this small fixture, the axis where prompt-only Slime shows value is
   **speculative extensibility / premature abstraction**. The refactor and
   vague-scope baits need a stronger setup (or a more eager baseline) to fire.

## What this does and does not support

- Supports: Slime's discipline can prevent speculative abstraction when the
  prompt invites it (1 task, 1 run — a signal, not a result).
- Does not support: any general patch-cost reduction. 2 of 3 baited tasks showed
  no baseline excess to trim. No efficacy claim; README stays experimental.

## Next

- Add 2–3 more extensibility-style tasks (the axis that fires) and repeat with
  ≥3 runs each to see if DA1 holds beyond one sample.
- Strengthen the refactor/gold-plating baits, or model the eager-baseline
  failure mode explicitly, so DA2/DA3-style axes become testable.
- Then run the same set inside a hooked session (condition C) to check the gates
  add anything beyond the prompt-only discipline.
