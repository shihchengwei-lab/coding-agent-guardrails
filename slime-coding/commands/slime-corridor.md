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
3. Determine the **Meeting Corridor**: the minimal set of files/edits that
   connects an attachment point to a required behaviour. Express the allowed
   surface as a list of path globs.
4. Write `.slime/corridor.md` with exactly this shape:

   ```markdown
   # Corridor: <short-id>

   ## Scope
   <one or two lines: what the minimal change is>

   ## Paths
   - <glob of an allowed file/dir, e.g. lib/feature/x/**>
   - <glob ...>

   ## Goal Frontier
   - <necessary behaviour, traced to an acceptance criterion>

   ## Start Frontier
   - <attachment point: file:symbol>

   ## Stop Condition
   - <the observable check/test/behaviour that means done>
   ```

5. Keep it terse — a map, not a spec. Create the `.slime/` directory if needed.
6. Confirm to me the corridor id and the `## Paths` you committed to, because
   the L2 gate and L3 measurement read exactly those.
