---
description: Record a rejected design path in .slime/PRUNED.md so it can't be silently revived.
argument-hint: "[what you rejected and why]"
---

Append a pruned-path record to `.slime/PRUNED.md`. The argument, if given,
describes what was rejected and why: $ARGUMENTS

Steps:

1. Identify the design path that was considered and rejected this round, and
   the concrete reason it was pruned (adds a dependency, widens the blast
   radius, no attachment point in the repo, speculative generality, contradicts
   an acceptance criterion, etc.). If the argument already states it, use that;
   otherwise infer it from the current task and confirm with me.
2. Read `.slime/corridor.md` (if present) to get the current corridor id and
   round context.
3. Append a record to `.slime/PRUNED.md` in exactly this shape (create the
   file and `.slime/` directory if missing):

   ```markdown
   ## [YYYY-MM-DD] corridor:<id>
   **Pruned:** <the rejected design, one line>
   **Reason:** <why it has no evidence / why it loses>
   **Revive only if:** <the new evidence that would change the verdict>
   ```

   Use today's date. The `corridor:<id>` tag matters — the injection hook uses
   it to decide which records are relevant to the current corridor.
4. Do NOT rewrite or prune existing records; only append. Old records stay on
   disk for the record; the decay logic decides what re-enters context.
5. Confirm the one-line summary you recorded.
