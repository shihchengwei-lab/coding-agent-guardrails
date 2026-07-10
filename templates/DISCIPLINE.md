<!-- Unified coding discipline for the toolkit — the single source.
     The one-command installer writes this block into the consuming
     project's CLAUDE.md and AGENTS.md; install-codex.ps1 reads the same
     file. Distilled from kiss-my-diff/AGENT.md (kept verbatim as the
     benchmark's measured specimen) and the former slime-coding discipline
     templates, which were removed at monorepo fusion. -->

## Coding Discipline

Optimize for the **smallest sufficient semantic displacement**: make the
smallest readable change that fully satisfies the observable goal. Do not trade
fewer lines for hidden state, extra assumptions, or more context required to
understand the result. Preserve existing APIs, data flow, module boundaries,
naming, and architecture unless the corridor explicitly allows moving them.

Rules:

1. Build only what is needed now.
2. Read the existing code before editing.
3. Use existing helpers and patterns before adding new code; use built-ins
   before adding dependencies.
4. Prefer the smallest sufficient readable change; touch the fewest files
   needed, but do not optimize line count at the expense of total complexity.
5. Do not add abstractions for one-shot code.
6. Do not hide errors or invalid states.
7. Verify with the smallest relevant test.
8. Stop at the **Stop Condition** — the observable check that means done.
   No gold-plating past it.

Process (uses the slime-coding hooks installed in this project):

1. Do not generate code straight from the prompt. Grow the **Goal Frontier**
   (necessary observable outcomes, constraints, and unknowns, read backwards
   from the acceptance criteria) and the **Start Frontier** (real attachment
   points in this repo) separately. Read broadly enough to understand the
   existing flow; edit narrowly. Use the `slime-navigate` skill.
2. Edit only inside the **Meeting Corridor** — the minimal files where the two
   frontiers meet. Write it to `.slime/corridor.md` with `/slime-corridor`
   before editing. Choose `trivial`, `normal`, or `high` rigor. Normal and high
   corridors must state both the evidence supporting the route and what would
   falsify it; high rigor also names failure, rollback, and an independent
   check. Leaving the corridor requires new evidence and an update.
3. **Before editing, read `.slime/PRUNED.md`.** Do not revive a rejected
   design without new evidence. When you delegate editing to a sub-agent,
   copy the relevant pruned summary into its task prompt.
4. When you reject a design path, record it with `/slime-prune` (the
   abandoned path + the reason).

Evidence & handoff (agentcam — do this without being asked):

1. After your change passes its tests, run them once more under the
   recorder: `agentcam verify -- <project test command>`. It runs the
   check itself and records command, exit code, and duration as observed
   facts. If it errors because nothing is being recorded (no wrapped
   run and no in-progress recorded session), skip steps 2–3 and say so.
2. When preparing the PR: `agentcam handoff` prints the five-line
   handoff drafted from the record. Paste it into the PR body, fill in
   `Decision` yourself, and leave `Verified` as the fill-in unless a
   recorded check actually passed.
3. Attach the evidence: `agentcam export latest --files .agentcam/` and
   commit that directory with the PR, so corridor-ci can append the
   recorded evidence to its report.

Self-report explains intent; observed evidence determines confidence. Never
hand-write facts these tools measure: no invented `Verified` lines, no edited
exit codes. Label manual checks as manual, and state when observation was only
partial.
