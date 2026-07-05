<!-- Slime Coding Codex: L0 discipline.
     This block is installed into AGENTS.md. AGENTS.md is a durable Codex
     instruction surface, but still a soft constraint: the model can drift.
     The hard teeth live in the Codex hooks and git facts. -->

## Slime Coding

Optimize for **minimal semantic displacement**, not merely the fewest lines of
code: change the required behavior while preserving existing APIs, data flow,
module boundaries, naming, and architecture unless the corridor explicitly
allows moving them.

Do not generate code straight from the prompt. For any task that changes code:

1. Grow the **Goal Frontier** (necessary behaviors, read backwards from the
   acceptance criteria) and the **Start Frontier** (real attachment points in
   this repo) separately.
2. Edit only inside the **Meeting Corridor**: the minimal files where the two
   frontiers meet. Write it to `.slime/corridor.md` before editing, including
   Semantic Delta, Paths, and Non-goals. Leaving the corridor requires new
   evidence and an updated corridor.
3. Before editing, read `.slime/PRUNED.md`. Do not revive a rejected design
   without new evidence. When you delegate editing to a sub-agent, copy the
   relevant pruned summary into its task prompt; sub-agents have their own
   context.
4. When you reject a design path, append it to `.slime/PRUNED.md` with the
   abandoned path and the reason.
5. Stop at the **Stop Condition**: the observable check that means done. No
   gold-plating past it.
