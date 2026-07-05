<!-- Unified coding discipline for the toolkit.
     Merged from kiss-my-diff/AGENT.md and slime-coding/templates/CLAUDE.slime.md.
     The one-command installer pastes this single block into the consuming
     project's CLAUDE.md / AGENTS.md. The standalone rule files in each tool
     stay unchanged for standalone use. -->

## Coding Discipline

Optimize for **minimal semantic displacement**: change only the behaviour this
task requires, and preserve existing APIs, data flow, module boundaries,
naming, and architecture unless the corridor explicitly allows moving them.

Rules:

1. Build only what is needed now.
2. Read the existing code before editing.
3. Use existing helpers and patterns before adding new code; use built-ins
   before adding dependencies.
4. Prefer the smallest readable change; touch the fewest files needed.
5. Do not add abstractions for one-shot code.
6. Do not hide errors or invalid states.
7. Verify with the smallest relevant test.
8. Stop at the **Stop Condition** — the observable check that means done.
   No gold-plating past it.

Process (uses the slime-coding hooks installed in this project):

1. Do not generate code straight from the prompt. Grow the **Goal Frontier**
   (necessary behaviours, read backwards from the acceptance criteria) and the
   **Start Frontier** (real attachment points in this repo) separately. Use
   the `slime-navigate` skill.
2. Edit only inside the **Meeting Corridor** — the minimal files where the two
   frontiers meet. Write it to `.slime/corridor.md` with `/slime-corridor`
   before editing, including Semantic Delta and Non-goals. Leaving the
   corridor requires new evidence and an update.
3. **Before editing, read `.slime/PRUNED.md`.** Do not revive a rejected
   design without new evidence. When you delegate editing to a sub-agent,
   copy the relevant pruned summary into its task prompt.
4. When you reject a design path, record it with `/slime-prune` (the
   abandoned path + the reason).
