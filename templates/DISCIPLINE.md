<!-- Unified coding discipline for the toolkit — the single source.
     The one-command installer writes this block into the consuming
     project's CLAUDE.md and AGENTS.md. Distilled from
     kiss-my-diff/AGENT.md (kept verbatim as the
     benchmark's measured specimen) and the former slime-coding discipline
     templates, which were removed at monorepo fusion. -->

## Coding Discipline

Optimize for the **smallest sufficient semantic displacement**: make the
smallest readable change that fully satisfies the observable goal. Do not trade
fewer lines for hidden state, extra assumptions, or more context required to
understand the result. Preserve existing APIs, data flow, module boundaries,
naming, and architecture unless the task explicitly requires moving them.

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
8. Stop when the observable result is true and the installed checks pass.
   No gold-plating past it.

Process (the installed Guardrails hooks enforce this without user setup per task):

1. Do not generate code straight from the prompt. Read backwards from the
   acceptance criteria and forwards from real attachment points in this repo
   until you can name one observable **Outcome**. Read broadly enough to
   understand the existing flow; edit narrowly.
2. Before the first product edit, declare the observable outcome and minimal
   intended paths yourself; do not ask the user to fill a file:
   `guardrails internal scope set --outcome "..." --path path [--path path]`.
3. If repo evidence later requires another path, record the concrete reason
   before editing it:
   `guardrails internal scope add --path path --reason "..."`.
4. Do not invoke `guardrails approve`; high-risk approval belongs to the user.

Evidence & handoff (automatic at Stop):

1. Do not run a second `agentcam verify`, handoff, or export workflow. The Stop
   coordinator runs trusted checks once, finalizes the local record, and writes
   `.guardrails/review.json`.
2. When the user asks you to commit or open a PR, include that review artifact
   with the product change. Do not auto-stage or auto-commit it before then.
3. After opening a dependency or workflow PR, run
   `guardrails internal pr-sync`; it posts a head-bound approval only when a
   matching user high-risk confirmation exists.

Never hand-edit `.guardrails/review.json`; if it is stale, let Stop regenerate
it from the final state. Self-report explains intent; observed evidence
determines confidence.
