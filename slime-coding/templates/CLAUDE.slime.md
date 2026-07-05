<!-- Slime Coding — L0 discipline.
     Paste this block into the consuming project's CLAUDE.md. CLAUDE.md is a
     request, not a hard rule: the model can skip it, so this only carries the
     discipline. The teeth live in the L1/L2/L3 hooks. Note the built-in
     Explore/Plan sub-agents do NOT load CLAUDE.md, so this binds the main
     agent only — keep exploration discipline on the main agent. -->

## Slime Coding

Optimize for **minimal semantic displacement**, not merely the fewest lines of
code: change the required behaviour while preserving existing APIs, data flow,
module boundaries, naming, and architecture unless the corridor explicitly
allows moving them.

Do not generate code straight from the prompt. For any task that changes code:

1. Grow the **Goal Frontier** (necessary behaviours, read backwards from the
   acceptance criteria) and the **Start Frontier** (real attachment points in
   this repo) separately. Use the `slime-navigate` skill.
2. Edit only inside the **Meeting Corridor** — the minimal files where the two
   frontiers meet. Write it to `.slime/corridor.md` with `/slime-corridor`
   before editing, including Semantic Delta and Non-goals. Leaving the corridor
   requires new evidence and an update.
3. **Before editing, read `.slime/PRUNED.md`.** Do not revive a rejected design
   without new evidence. When you delegate editing to a sub-agent, copy the
   relevant pruned summary into its task prompt — sub-agents have their own
   context and do not see the main session's injected state.
4. When you reject a design path, record it with `/slime-prune` (the abandoned
   path + the reason). The Stop gate will block on failing checks if you don't.
5. Stop at the **Stop Condition** — the observable check that means done. No
   gold-plating past it.
