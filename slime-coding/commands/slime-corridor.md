---
description: Define or update the Slime Coding Meeting Corridor for the current task (.slime/corridor.md).
argument-hint: "[corridor id or short task description]"
---

Establish the Meeting Corridor for the current task. The argument, if given,
is the corridor id / task description: $ARGUMENTS

Steps:

1. If `.slime/corridor.md` already exists, read it and treat this as an update.
2. Read backwards from the acceptance criteria and forwards from the existing
   repo until you can name one observable outcome and the real attachment path.
3. Choose `trivial`, `normal`, or `high` rigor. Use trivial only for one local
   product file with no dependency or boundary change. Use normal by default.
   Use high when failure containment, rollback, and an independent check are
   necessary.
4. Determine the **Meeting Corridor**: the minimal sufficient paths connecting
   the existing attachment point to the required outcome.
5. Write `.slime/corridor.md`. The normal shape is:

   ```markdown
   # Corridor: <short-id>

   ## Rigor
   normal

   ## Outcome
   <the observable result that must become true and what must remain unchanged>

   ## Paths
   - <glob of an allowed file/dir, e.g. lib/feature/x/**>
   - <glob ...>

   ## Evidence
   - Supports: <repo/test/log evidence supporting this route>
   - Would falsify: <cheapest observation that would prove this route wrong>
   - Dependency: <package> — <why the outcome requires it>  # only when adding one

   ## Stop Condition
   - Command: <the command that must exit 0>
   # or: - Manual: <the observable behavior to inspect>
   ```

   For trivial, keep only Outcome, Rigor, Paths, and Stop Condition. For high,
   use the normal shape and append:

   ```markdown
   ## Controls
   - Failure mode: <what can go wrong>
   - Rollback: <how to contain or reverse it>
   - Independent check: <a check separate from the implementation path>
   ```

6. Keep it terse — a map, not a spec. Create the `.slime/` directory if needed.
7. Confirm the corridor id, rigor, outcome, and `## Paths` you committed to.
