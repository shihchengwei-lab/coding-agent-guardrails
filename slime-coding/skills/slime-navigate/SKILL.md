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

## Navigation method and artifact

Choose a rigor level, use the two frontiers to find the route, then persist only
the compact execution contract. Keep it short — this is a map, not a spec.

- **trivial** — one local product file and no dependency or boundary change:
  Outcome, Paths, and Stop Condition only.
- **normal** — the default: Outcome, Paths, supporting/falsifying Evidence, and
  Stop Condition.
- **high** — normal plus a failure mode, rollback, and independent check.

Existing corridors without a Rigor section remain legacy-compatible. New
corridors must state `trivial`, `normal`, or `high` explicitly.

1. **Goal Frontier** — work *backwards* from the acceptance criteria. What
   behaviours are strictly necessary for the criteria to pass? List them. Each
   item must trace to a criterion; if it doesn't, it isn't on the frontier.

2. **Start Frontier** — work *forwards* from the repo as it is. What existing
   functions, types, and seams can the change attach to? Read first. List the
   real attachment points (file + symbol), not hypothetical ones.

3. **Outcome and Meeting Corridor** — where the two frontiers touch: one
   observable result plus the *minimal* set of
   files/edits that sufficiently connects an attachment point to every required
   behaviour.
   This is the only place you are allowed to write. Anything outside it needs
   new evidence. Minimize semantic displacement, not just LOC: name the
   result and the existing boundary that must stay still. The frontiers are a
   navigation method, not extra form fields; persist their conclusion as
   `## Outcome` and `## Paths`.

4. **Evidence and falsifier** — cite what supports the chosen attachment point
   and state the cheapest observation that would prove this route wrong. Seek
   disconfirming evidence before committing to the patch.

5. **Pruned Paths** — only designs you actually considered and rejected, each
   reason (more deps, wider blast radius, no attachment point, speculative
   generality). Append these to `.slime/PRUNED.md` so the next round can't
   silently revive them. Use `/slime-prune`.

6. **Stop Condition** — preferably `Command: <command>` so the Stop hook runs
   it and blocks until exit 0. Use `Manual:` only when no command can observe
   the outcome.

## Write the corridor down

Persist the selected tier's Outcome, Paths, Evidence, and Stop Condition to
`.slime/corridor.md` (use `/slime-corridor`). Normal and high Evidence must
contain `Supports:` and `Would falsify:`. When adding a dependency, add
`Dependency: <package> — <reason>` or the Stop gate rejects it. High additionally
includes `## Controls` with `Failure mode:`, `Rollback:`, and
`Independent check:`.

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
