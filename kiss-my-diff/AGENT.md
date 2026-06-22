# Occam Agent Discipline

Use this as a compact standing instruction set for coding agents.

- YAGNI: Build only what is needed now; prefer one-liner solutions when they are clear and enough.
- KISS: Choose the simplest design that works; do not hide simple behavior behind ceremony.
- DRY: Remove real duplication; do not abstract two examples before the pattern is stable.
- Small diffs: Touch the fewest files needed; leave unrelated code alone.
- Read first: Inspect existing patterns before adding new code.
- Prefer built-ins: Use the language, framework, or repo utilities before adding dependencies.
- Explicit assumptions: State what is known, inferred, and missing before leaning on it.
- Tests prove behavior: Add or run the smallest test that covers the change.
- Verify output: Check the actual current result before saying it is done.
- Fail clearly: Surface errors with useful context; do not silently swallow failures.
- Preserve intent: Keep the user's goal and existing behavior unless asked to change it.
- Stop at done: Do not expand scope after the task is solved.
