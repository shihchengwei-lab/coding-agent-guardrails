---
description: Define or update the Slime Coding Meeting Corridor for the current task (.slime/corridor.md).
argument-hint: "[corridor id or short task description]"
---

Establish the Meeting Corridor for the current task. The argument, if given,
is the corridor id / task description: $ARGUMENTS

Steps:

1. If `.slime/corridor.md` already exists, read it and treat this as an update.
2. Derive the two frontiers for the task (use the `slime-navigate` skill's
   method): the **Goal Frontier** (necessary behaviours, read backwards from
   the acceptance criteria) and the **Start Frontier** (real attachment points
   in the repo — read the relevant files first, cite file + symbol).
3. Choose `trivial`, `normal`, or `high` rigor. Use trivial only for one local
   product file with no dependency, public API, data-flow, ownership, security,
   or architecture change. Use normal by default. Use high when the author
   judges rollback and an independent check necessary.
4. Determine the **Meeting Corridor**: the minimal sufficient set of files/edits that
   connects an attachment point to a required behaviour. Express the allowed
   surface as a list of path globs. Also name the semantic displacement: what
   behaviour/concept moves, and what existing boundaries must stay still.
5. Write `.slime/corridor.md`. The normal shape is:

   ```markdown
   # Corridor: <short-id>

   ## Scope
   <one or two lines: what the minimal change is>

   ## Rigor
   normal

   ## Semantic Delta
   - This task changes: <the smallest observable behaviour/concept that must move>
   - This task preserves: <existing API/data flow/component boundary/naming/ownership>

   ## Non-goals
   - <architecture/API/dependency/refactor path that is not part of this task>

   ## Paths
   - <glob of an allowed file/dir, e.g. lib/feature/x/**>
   - <glob ...>

   ## Goal Frontier
   - <necessary behaviour, traced to an acceptance criterion>

   ## Start Frontier
   - <attachment point: file:symbol>

   ## Evidence
   - Supports: <repo/test/log evidence supporting this route>
   - Would falsify: <cheapest observation that would prove this route wrong>

   ## Stop Condition
   - <the observable check/test/behaviour that means done>
   ```

   For trivial, keep only Scope, Rigor, Paths, and Stop Condition. For high,
   use the normal shape and append:

   ```markdown
   ## High-risk Controls
   - Failure mode: <what can go wrong>
   - Rollback: <how to contain or reverse it>
   - Independent check: <a check separate from the implementation path>
   ```

6. Keep it terse — a map, not a spec. Create the `.slime/` directory if needed.
7. Confirm to me the corridor id, rigor, and `## Paths` you committed to, because
   the L2 gate and L3 measurement read exactly those.
