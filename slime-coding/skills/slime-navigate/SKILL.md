---
name: slime-navigate
description: Slime Coding frontier navigation. Use BEFORE writing or editing any code for a non-trivial task — grow the requirement frontier and the repo frontier separately, then edit only the minimal corridor where they meet. Invoke when starting a feature, fix, or refactor, when the task says "implement / add / change X", or whenever you are tempted to generate code straight from the prompt. Produces .slime/corridor.md and feeds .slime/PRUNED.md.
---

# Slime Coding — frontier navigation

Do not generate code straight from the prompt. Let the requirement and the
existing repo each grow a frontier, advance them toward each other, and only
act inside the narrow corridor where they meet. Prune paths with no evidence
and record why.

## When this applies

Any task that changes code and can be stated as observable acceptance
criteria. If the requirement cannot be written as something observable, stop
and do discovery first — Slime Coding has nothing to constrain yet.

## The five outputs

Choose a rigor level, then produce the required outputs before editing. Keep
them short — this is a map, not a spec.

- **trivial** — one local product file, no dependency or public/API boundary
  change: Scope, Paths, and Stop Condition only.
- **normal** — the default: the full frontiers, semantic delta, non-goals, and
  evidence below.
- **high** — normal plus a failure mode, rollback, and independent check.

Existing corridors without a Rigor section remain legacy-compatible. New
corridors must state `trivial`, `normal`, or `high` explicitly.

1. **Goal Frontier** — work *backwards* from the acceptance criteria. What
   behaviours are strictly necessary for the criteria to pass? List them. Each
   item must trace to a criterion; if it doesn't, it isn't on the frontier.

2. **Start Frontier** — work *forwards* from the repo as it is. What existing
   functions, types, and seams can the change attach to? Read first. List the
   real attachment points (file + symbol), not hypothetical ones.

3. **Meeting Corridor** — where the two frontiers touch: the *minimal* set of
   files/edits that sufficiently connects an attachment point to every required
   behaviour.
   This is the only place you are allowed to write. Anything outside it needs
   new evidence. Minimize semantic displacement, not just LOC: name the
   behaviour/concept that moves and the existing API, data flow, ownership,
   naming, or architecture boundary that must stay still.

4. **Evidence and falsifier** — cite what supports the chosen attachment point
   and state the cheapest observation that would prove this route wrong. Seek
   disconfirming evidence before committing to the patch.

5. **Pruned Paths** — the designs you considered and rejected, each with the
   reason (more deps, wider blast radius, no attachment point, speculative
   generality). Append these to `.slime/PRUNED.md` so the next round can't
   silently revive them. Use `/slime-prune`.

6. **Stop Condition** — the observable signal that says "done": the check,
   test, or behaviour that, once green, means stop. No gold-plating past it.

## Write the corridor down

Persist the outputs required by the selected rigor to `.slime/corridor.md`
(use `/slime-corridor`) so the L2 corridor gate and the L3 out-of-corridor
measurement can read them. Normal and high corridors include `## Evidence`
with `Supports:` and `Would falsify:` items. High additionally includes
`## High-risk Controls` with `Failure mode:`, `Rollback:`, and
`Independent check:` items.

## Before editing

- Read `.slime/PRUNED.md`. Do not re-propose a rejected path without new
  evidence; if you delegate editing to a sub-agent, copy the relevant pruned
  summary into its task prompt — sub-agents have their own context and do not
  see the main session's injected state.
- Read broadly; edit narrowly. Stay inside the corridor. If you find you must leave it, that is new
  evidence: update the corridor (and say why) rather than quietly widening it.

## The discipline in one line

No code without a sufficient corridor; no normal/high corridor without support
and a falsifier; no pruned path without a recorded reason.
