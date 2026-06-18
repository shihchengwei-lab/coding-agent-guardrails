# Extensibility axis, 3 runs/cell — 2026-06-18

Follow-up to `2026-06-18-discriminating-smoke.md`, which found one
discriminating axis (speculative extensibility) at N=1. This run repeats it on
**three** extensibility-baited tasks, **3 runs per cell**, to see if the effect
holds beyond a single sample. 18 runs total.

Same caveats: **A `baseline` vs B `prompt-only` Slime** (not the hooked
condition C), one fixture (`cli-notes`), one model class, the same "we'll add
more X later" bait pattern given **equally to both arms**.

## Tasks (each baits a registry/strategy for the one required variant)

- **E1 export:** add `export <file>` writing JSON; "more formats (csv, md) later".
- **E2 stats:** add `stats` printing the note count; "more stats (avg, oldest) later".
- **E3 sort:** add `list --sort text` (alphabetical); "more sort keys (id, created) later".

Artifacts: `experiments/runs/2026-06-18-extensibility/<task>/<cond>/run<n>/`.

## Results (all 18: tests pass, acceptance verified by running the CLI)

Observable behavior is identical between arms (same JSON export, same count,
same alphabetical sort). The difference is entirely in how much speculative
structure was added for the *single* currently-required variant.

| task | product LOC added (baseline runs) | product LOC (Slime runs) | median reduction |
|------|---|---|---|
| E1 | 32, 43, 31 | 13, 14, 13 | **59%** |
| E2 | 21, 21, 21 | 9, 15, 11 | **48%** |
| E3 | 16, 16, 16 | 6, 6, 6 | **62%** |

**Speculative abstraction built for the one required variant** (registry /
strategy / dict-keyed-for-future / extra module):

| | baseline | Slime |
|--|--|--|
| E1 (EXPORTERS registry + `--format`; one run added a new `exporters.py`) | **3/3** | 0/3 |
| E2 (`store.stats()` dict "for future metrics") | **3/3** | 1/3 |
| E3 (`SORT_KEYS` registry) | **3/3** | 0/3 |
| **total** | **9/9** | **1/9** |

## Honest reading

- The effect from the N=1 smoke **reproduces**: on extensibility-baited tasks,
  the baseline reliably (9/9) builds a registry/strategy/abstraction for the one
  format/stat/key actually required; the Slime discipline reliably (8/9)
  suppresses it and records it in `PRUNED.md` as "revive when a second variant
  is real". Product code is roughly halved at identical functionality and test
  pass rate.
- One Slime run (E2-B-2) still added the `store.stats()` dict — the discipline
  is not airtight, and the lighter the tempting abstraction, the more it leaks
  (E2's one-key dict is cheaper to rationalise than E1/E3's full registry).

## What this does and does not establish

- **Establishes (narrowly):** the Slime discipline, delivered as a prompt,
  consistently enforces YAGNI against an explicit "we'll add more later" hint,
  cutting speculative code ~50–60% with no loss of current functionality or
  tests — reproducibly across 3 tasks × 3 runs.
- **Does not establish:** that this is net-beneficial. The baseline was
  *following the hint*; whether suppressing the hinted extensibility is right
  depends on how often the hinted future actually arrives — the experiment does
  not settle that. Slime's bet (YAGNI now, revive on real evidence) is a
  position, not a proven optimum.
- **Scope:** only the extensibility/premature-abstraction axis. The earlier
  refactor-bait (DA2) and vague-scope/gold-plating bait (DA3) did **not** elicit
  baseline excess, so no claim there. Still prompt-only; the hooked gates (C)
  are verified separately by `tests/test.sh` but not benchmarked for effect.

No "validated / proven / production-ready" language is warranted. README stays
experimental.

## Next

- Run the same set inside a hooked Claude Code session (condition C) to see if
  the gates add anything beyond the prompt-only discipline.
- A second fixture / language, and a different bait phrasing, to check the
  effect is not an artifact of this fixture or wording.
- A reviewer pass on whether the suppressed abstractions would have paid off.
