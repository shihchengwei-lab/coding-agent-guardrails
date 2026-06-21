# Model-class probe — does the hooked stack behave the same on Haiku/Sonnet? — 2026-06-22

Follow-up to `2026-06-21-bvc.md`, which left the caveat **"one model class"**.
The 06-21 verdict ("L0 prose carries the suppression; the hooked gates add no
further cut on the speculative-extensibility axis") was measured on Opus-class
runs only. This run repeats the **hooked-slime** column of BvC on two more
model classes — **Sonnet 4.6** and **Haiku 4.5** — to see whether the 06-21
"prose does the work" generalisation holds, or whether weaker models break it.

**Headline (N=3/cell, 9 cell/model, hooked-slime only):**
- **No model in the set blows the gates open with a registry pile-up.**
  Registry / dict-keyed extension point built for the single required variant:
  Opus 3/9 (06-21 reuse), Sonnet 1/9, Haiku 0/9.
- **Sonnet shows a new failure mode the 06-21 run never saw: 2/9 cells
  finished with an empty diff — the agent spent the 590 s timeout on
  corridor / repo navigation and never wrote the implementation.** Haiku and
  Opus did not exhibit this.
- **No baseline (no-hook) was run on Haiku/Sonnet.** The question "does Slime
  help / hurt weak models relative to no-Slime?" is **not answered here**. The
  numbers below describe behaviour **under hooks only**.

## Scope (what this run is and isn't)

- **Is**: hooked-slime condition only, N=3 per (task × model), Python `cli-notes`
  fixture, same three baits (E1 export / E2 stats / E3 sort) as the
  extensibility report. Same one-shot `claude -p` modality as 06-21 BvC's C arm.
- **Isn't**: a baseline comparison (no A/B arms for Haiku/Sonnet) — so this run
  CANNOT say "Slime helps Haiku" or "Slime hurts Sonnet". It only describes
  what hooked-slime cells look like across model classes. The 06-21 BvC's B-vs-C
  null was measured at one model class; that null is not re-measured here, and
  is not generalised to Haiku/Sonnet either.

## Setup

- Harness: `experiments/run-bvc.sh` extended with a `BVC_MODEL` env var that
  passes `--model <id>` to `claude -p`. No `--model` flag = CLI default
  (unchanged behaviour for the 06-21 runs). Verified the flag reaches the
  agent: each cell's stdout banner reads `agent run (model=claude-haiku-4-5)`
  or `agent run (model=claude-sonnet-4-6)`.
- Model ids: `claude-haiku-4-5`, `claude-sonnet-4-6`. Opus-class numbers reused
  from 2026-06-21-bvc.md unchanged.
- Cells: `experiments/runs/2026-06-22-haiku-bvc/`, `2026-06-22-sonnet-bvc/`.
  Probe cells (single-task pre-flight) at `…-haiku-probe-bvc/` and
  `…-sonnet-probe-bvc/`; the Sonnet probe showed an E1 timeout-on-navigation
  that recurred at scale (see below) — keeping the probes around for traceability.

## Counts — registry / dict-keyed extension points (N=3/cell)

The rubric matches 06-21 BvC: count runs that built **a registry / strategy /
dict-keyed-for-future / extra module** for the *one* currently-required variant.

| task | Opus C (06-21) | **Sonnet C (new)** | **Haiku C (new)** |
|------|:---:|:---:|:---:|
| E1 export | 0/3 | 0/3 | 0/3 |
| E2 stats  | 0/3 | 0/3 | 0/3 |
| E3 sort   | **3/3** | **1/3** (run3 `_SORT_KEYS`) | **0/3** |
| **registry total** | **3/9** | **1/9** | **0/9** |

E3 is the only task with a registry signal in this matrix. E1/E2 are clean
across all three models — consistent with the 06-21 finding that E3 is the
lightest bait and the one that leaks first.

## Counts — timeouts (empty diff on a 590 s budget)

A cell is counted as "timeout" if the agent exit was 0 but `git diff HEAD --
cli_notes tests` produced zero bytes. The agent authored a corridor (visible
in transcripts) but never wrote the implementation before being killed.

| model | timeout cells | cells |
|-------|:---:|---|
| Opus (06-21) | 0/9 | not reported in 06-21 (logs available, no signal observed in counts) |
| **Sonnet** | **2/9** | E1 run3, E3 run2 |
| **Haiku** | 0/9 | — |

Sonnet's two timeouts are the most surprising result in this run. The
transcripts (e.g. `_logs/E1-hooked-slime-run3.jsonl`) show the agent doing
heavy frontier work — Read/Glob/Grep across the fixture, Skill + Agent tool
calls — and producing a committed corridor as its final visible action, before
the 590 s wall hits.

## Cross-task code-shape notes (qualitative, on top of the counts)

- **E3 `--sort` is leaky across all three models in a way the registry-only
  count doesn't capture.** Even cells that didn't build a dict often widened
  the surface beyond the literal task:
  - Haiku E3 run2 wrote `sorted(notes, key=lambda n: n[args.sort])` — no
    whitelist, accepts any key. Counted as 0 by the registry rubric, but is a
    real over-extension.
  - Haiku E3 run3 wrote `if args.sort == "text"` but the argparse help string
    advertises "sort by key (text, id, created)" — code minimal, prose leaks.
  - Sonnet E3 run3 (the registry cell) used `choices=list(_SORT_KEYS)` — the
    cleanest "I built an extension point" signature in the run.
  - Sonnet E3 run1 (minimal) used `choices=["text"]` explicitly — the
    tightest cell on E3 in the whole matrix.
- **E1/E2 cells all look the same across models**: a 3-line `cmd_export` /
  `cmd_stats` plus a couple of straightforward tests. No FORMATS dict, no
  STAT_HANDLERS, no strategy classes. This is consistent with the
  extensibility report's finding that E1/E2 are heavier baits and need
  E3-strength leak conditions to fire.

## What this lets us claim (and what it doesn't)

**Holds:**
- The hooks **run end-to-end on Haiku and Sonnet** under one-shot `claude -p`.
  No crash, no permission failure, no harness bug specific to a model class.
- The registry-leak signal that 06-21 attributed to model behaviour at one
  model class **does not get worse on smaller models** in this matrix; Sonnet
  and Haiku both produced fewer registry cells than Opus.

**Does not hold (cannot be claimed):**
- "Hooks don't hurt." Sonnet's 2/9 timeout is a real cost imposed by the
  corridor-first flow consuming the wall-clock budget. At a 590 s ceiling, a
  model that spends ~590 s on navigation never reaches the implementation.
  This may not reproduce at a larger timeout, but at this configuration it is
  a measured rate, not a fluke.
- Any generalisation to non-Python fixtures or to baits other than the
  extensibility axis. None tested here.

## Update — baseline arm added (2026-06-22 evening)

The "no baseline" gap was closed by running condition A (baseline: naked
fixture, no L0 prose, no hooks) on the same Haiku/Sonnet × E1/E2/E3 × N=3
matrix. Same one-shot `claude -p` modality.

| model | condition | registry | code-level over-ext | timeout |
|-------|-----------|:---:|:---:|:---:|
| Haiku  | baseline (A)   | 0/9 | 0/9 | 0/9 |
| Haiku  | hooked-slime (C) | 0/9 | 1/9 (E3 run2 generic `args.sort`) | 0/9 |
| Sonnet | baseline (A)   | 0/9 | 0/9 | 0/9 |
| Sonnet | hooked-slime (C) | 1/9 (E3 run3 `_SORT_KEYS`) | 0/9 | 2/9 (E1 run3, E3 run2) |
| Opus   | hooked-slime (C, 06-21 reuse) | 3/9 | 3/9 | 0/9 |

### What the baseline shows

- **Both models stayed clean on baseline.** Haiku/Sonnet, given the
  speculative-extensibility bait with no L0 prose and no hooks, did not build
  a registry on any of the 18 cells, and did not over-extend the code.
- **Adding Slime did not measurably help on this axis.** For Haiku and
  Sonnet, baseline is at least as clean as hooked-slime — there is no cell
  where the hooks suppressed something baseline failed to suppress.
- **Adding Slime has a measurable cost on Sonnet at this configuration.**
  Two cells (2/9) burned the 590 s budget on corridor navigation in
  hooked-slime; the baseline arm finished all 9 cells without timing out.
  Plus one Sonnet hooked cell built a registry (`_SORT_KEYS`) where the
  baseline cells did not.

### Direct answer to "does Slime work on Haiku/Sonnet?"

**On this fixture, this bait, at N=3 per cell: no measurable positive effect
from Slime, plus measurable negative effects.** Specifically:

- The targeted failure mode (speculative registry pile-up) does not occur on
  Haiku/Sonnet baseline, so there is nothing for Slime to suppress that
  isn't already absent. This is consistent with the 06-21 BvC finding that
  the gates are a backstop on git facts, not a multiplier on premature
  abstraction — and extends it: on weaker models, the *prompt-only condition
  that 06-21 said carries the suppression isn't even needed* on this bait,
  because the model doesn't bite.
- The bundle imposes a wall-clock tax on Sonnet (corridor authoring + repo
  navigation eats the agent's deliberation budget). At 590 s this caused
  2/9 cells to produce no implementation at all.

### What this does NOT prove

- **N=3 is noise-level for any single delta.** "1/9 vs 0/9 registry" on
  Sonnet hooked is one cell; the same number would appear under sampling
  noise. The shape of the table (multiple deltas all in the same direction)
  is the load-bearing observation, not any individual cell.
- **Only one fixture, one bait family.** "Slime hurts weak models" is too
  strong; "On this specific extensibility-bait test, Slime has nothing to
  add for Haiku/Sonnet and adds a timeout cost on Sonnet" is what the data
  actually supports.
- **The hooks have separate, measured value as a backstop on git facts**
  (new dependencies, hallucinated references, failing checks at Stop) — none
  of which are tested here. Those gates didn't fire in this matrix because
  the agents didn't trigger them, not because they don't work.
- **One-shot modality.** A user driving an interactive Slime session can
  raise the timeout, can revise the corridor mid-flight, can stop the agent
  before it burns the budget. The one-shot `claude -p` modality doesn't
  give the model any of that.

### Effect on the README

The prior README bullet stayed neutral ("跨 model 也測過、但沒測 baseline").
That hedge is now obsolete and replaced with the actual finding: on weak
models tested here, Slime adds cost without adding measurable suppression on
this axis, because the suppression target isn't present in the baseline.

## Effect on the 06-21 verdict

The 06-21 BvC's "prose carries the suppression on this axis" finding was at
one model class. This run does **not** invalidate it — and does not extend
it. What it adds:

- A model-class spread for the C arm exists and is small (registry count
  3 → 1 → 0 as we move Opus → Sonnet → Haiku) — the direction is *toward*
  cleaner code on weaker models in this set, not the other way.
- A timeout cost shows up at Sonnet that 06-21 didn't surface. This is a new
  hooks-related signal worth tracking; it can't be cleanly attributed to "the
  hooks" vs "the agent's deliberation style under one-shot" without an A/B
  on the same model.

The README's prior text **"真正讓 AI 守規矩的，是寫在 prompt 裡的紀律。
關卡負責接住『紀律失靈』的那幾種情況"** was a generalisation from one model
class. It is qualified, not refuted, by this run: across three model classes
in the hooked condition, the picture stays consistent enough that the
claim's *direction* survives — but the README should disclose that no
baseline was tested for Haiku/Sonnet, and that Sonnet shows a navigation
cost the prior copy never mentioned.

## Artifacts

- Cells + metrics.json: `experiments/runs/2026-06-22-haiku-bvc/`,
  `2026-06-22-sonnet-bvc/`.
- Transcripts, diffs, pytest output: `_logs/` inside each.
- Probe cells (kept for traceability): `…-haiku-probe-bvc/`,
  `…-sonnet-probe-bvc/`.
- Runner change: `experiments/run-bvc.sh` (new `BVC_MODEL` env var; the
  existing default-no-flag behaviour is preserved).

## Scope / caveats

One fixture family (Python `cli-notes`), one bait family (extensibility axis),
**N=3 per (task × model)** — that is 27 cells of hooked-slime evidence in
this run, on top of the 06-21 Opus column being reused. No baseline arm on
the new models. No "validated / proven / production-ready" language is
warranted. README stays experimental.
