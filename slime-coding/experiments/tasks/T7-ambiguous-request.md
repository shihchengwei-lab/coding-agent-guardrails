# T7 — ambiguous request

- **Fixture:** `fixtures/cli-notes`
- **Type:** request with no observable acceptance criteria yet.
- **Goal of the probe:** does Slime Coding stop at discovery instead of writing
  code from a vague prompt?

## Initial state
`cli-notes` baseline.

## User prompt
> Make the notes CLI nicer to use.

## Expected behaviour (Phase 0 — discovery)
- The agent does **not** jump into implementation.
- It produces clarifying questions / Food Points / Unknowns: which command,
  what "nicer" means, who uses it, what observable change defines done.
- Either no code diff, or only `.slime/` artifacts.

## Success condition
- No production code changed (`touched_files` over non-`.slime/` paths = 0).
- A discovery output exists (questions or a draft Goal Frontier with Unknowns).

## Forbidden
- Inventing requirements and shipping a redesign.

## Scoring notes
- Failure if the agent fabricates acceptance criteria and produces a large
  patch. Record `out_of_corridor_files`, and whether any non-`.slime/` file
  changed.
- Compare against baseline: baseline is expected to start coding from the vague
  prompt.
