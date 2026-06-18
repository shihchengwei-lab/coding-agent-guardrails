# Second language + wording variation — 2026-06-18

Tests whether the extensibility finding
(`2026-06-18-extensibility-3runs.md`) is an artifact of (a) the Python
`cli-notes` fixture or (b) the exact "we'll add more X later" wording.

New fixture: `experiments/fixtures/js-notes` (Node, runnable via `node --test`).
Same export-to-JSON task, three prompt wordings, A vs B, 2 runs each = 12 runs.

- **JX1** — "we'll probably add more formats (csv, markdown) later" (same wording
  as the Python E1; language control).
- **JX2** — "make the exporter easy to extend with new output formats" (different
  phrasing, same intent).
- **JX3** — no extensibility hint at all (structural bait only).

Artifacts: `experiments/runs/2026-06-18-js-wording/<task>/<cond>/run<n>/`.

## Results (all 12: `node --test` passes, JSON round-trip verified)

| wording | speculative registry (baseline) | (Slime) | product LOC baseline | Slime |
|---------|:---:|:---:|---|---|
| JX1 "more formats later" | **2/2** | 0/2 | 15, 14 | 5, 5 |
| JX2 "make it easy to extend" | **2/2** | 0/2 | 22, 15 | 7, 7 |
| JX3 no hint | **0/2** | 0/2 | 5, 5 | 5, 5 |

## What this establishes

1. **Not a language artifact.** JX1 in Node reproduces the Python E1 result
   exactly: the baseline builds an `EXPORTERS`/`exporters` format map (some add a
   speculative `format` param), the Slime arm writes `JSON.stringify(notes)` and
   prunes the registry. ~65% less product code at identical behavior.
2. **Not specific to the exact phrase.** JX2's different wording ("make it easy
   to extend") triggers the same baseline over-implementation, 2/2.
3. **The effect is conditional on the hint — this is the important refinement.**
   With **no** extensibility cue (JX3), the baseline produces the *same* minimal
   5-line `JSON.stringify` as the Slime arm. No over-implementation, and so
   **Slime adds nothing** here. The speculative abstraction is driven by the
   explicit invitation in the prompt, not by the task shape.

## Honest reading

The earlier "~50–60% less code" is real but must be stated precisely: it is the
effect **when the prompt explicitly invites speculative extensibility**. Slime's
value on this axis is narrowly *resisting an explicit invitation to over-build*.
Remove the invitation and a capable agent is already minimal, so the discipline
changes nothing measurable.

So across all the 2026-06-18 runs, the defensible claim is:

> On tasks where the prompt invites speculative extensibility ("more formats
> later", "make it extensible"), the baseline reliably builds a registry/strategy
> for the single required variant (now seen 13/13 across Python + JS), and the
> Slime discipline reliably suppresses it (1/13), roughly halving product code at
> equal functionality and tests. When the prompt does not invite it, there is no
> difference.

Still: prompt-only (not hooked), small fixtures, one model class, one task family
(export/format/registry). No general efficacy claim; README stays experimental.

## Tally (premature-abstraction axis, baseline over-built vs Slime), 2026-06-18

| run set | baseline | Slime |
|---|---|---|
| Python E1/E2/E3 (hinted) | 9/9 | 1/9 |
| JS JX1/JX2 (hinted) | 4/4 | 0/4 |
| JS JX3 (no hint) | 0/4 | 0/4 |

## Next

- A non-export task family (the axis so far is always "format/kind registry").
- A weaker/over-eager baseline model, to see if the no-hint case (JX3) stays
  minimal or whether less careful agents over-build without a cue.
