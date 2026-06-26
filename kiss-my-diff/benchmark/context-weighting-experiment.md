# Context Weighting Experiment

This note explains why the benchmark includes prompt variants beyond the default
`AGENT.md`.

The short version: a coding agent is still built around a model generating the
next token from the context it was given. Natural-language instructions are
therefore soft pressure, not hard boundaries. They change what the model is more
likely to emit next, but they do not guarantee behavior. The benchmark is
looking for the sweet spot: enough context pressure to make the diff smaller,
without pushing the model into missing the task.

## The Model-Level View

For the kind of LLM coding agent this repo targets, the basic operation is not
"obey a rule" in the way a program obeys an `if` statement. The model receives a
context window and produces a probability distribution over possible next
tokens. Decoding then chooses tokens from that distribution. Those tokens become
text, code, shell commands, tool calls, or explanations, depending on the
harness around the model.

That is why `AGENT.md`, skills, prompts, and workflow files matter. They add
tokens to the context, and those tokens can raise the probability of some
continuations while lowering others. A rule like "touch the fewest files needed"
does not mechanically block a two-file edit. It makes a one-file edit more
likely when the model can see a plausible one-file path.

This is also why there is no literal "compliance" guarantee at the natural
language layer. The instruction can be ambiguous, outweighed by nearby task
details, forgotten in a long context, misapplied by the model, or traded off
against another instruction. Even with deterministic decoding, the output is
still selected from the model's learned distribution; the model is not executing
a rule engine.

## The Agent Loop

Agentic AI does not need a mysterious idea of autonomy to be useful. A practical
agent loop is more mechanical:

1. Text rules change the model's next-token distribution.
2. The harness interprets some generated tokens as executable requests.
3. The app, service, runtime, or OS executes those requests.
4. The result is fed back into the model as more context.
5. The loop continues until the task stops.

In that loop, `AGENT.md`, skills, prompts, and workflow files all live on the
soft side of control. They can make a model more likely to choose a small,
local, verified change, but they are still tokens in context.

## Why This Is a Soft Constraint

A hard constraint rejects or prevents an invalid action. A JSON schema can reject
the wrong shape. A validator can fail bad output. A sandbox can block filesystem
access. A permission prompt can stop a command. A test can fail a patch. CI can
refuse a merge. Deterministic code can return the same result for the same
input.

An `AGENT.md` file cannot do any of that by itself. It does not intercept tool
calls, reject patches, enforce permissions, or prove correctness. It only
changes the context used to generate the next tokens. That makes it useful, but
not authoritative.

The hard side of control lives outside the model: tool schemas, validators,
sandboxes, permissions, tests, CI, deterministic code, runtime constraints, OS
permissions, and human approval. If a step needs a guarantee, it belongs on that
hard side, not only in a prose instruction.

`kiss-my-diff` sits intentionally on the soft side. It is not a security
boundary and not a correctness guarantee. It is a small context nudge toward
smaller diffs.

## What Was Tested

The default file has 11 lines. I tested three extra variants to see whether the
signal should be strengthened, contrasted, or both:

- `weighted core`: repeats the smallest-correct-diff objective before the rule
  list.
- `contrast boundaries`: pairs positive rules with explicit "do not" boundaries.
- `weighted + contrast`: combines both approaches.

Each variant was run across the same 8 tasks and 4 models, for 32 runs per
variant.

### Exact Variant Text

`weighted core`:

```text
Optimize for the smallest correct diff.
Read first, reuse existing code, then make the smallest readable change.
Verify the relevant behavior, then stop.

Build only what is needed now.
Prefer the smallest readable change.
Read the existing code before editing.
Use existing helpers and patterns before adding new code.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Do not hide errors or invalid states.
Verify with the smallest relevant test.
Stop when done.
```

`contrast boundaries`:

```text
Read the existing code before editing; do not guess APIs, helpers, or patterns.
Use existing helpers and patterns before adding new code; do not duplicate helper logic.
Prefer the smallest readable change; do not rewrite nearby code just because you saw it.
Verify with the smallest relevant test; do not stop on an unverified change.

Build only what is needed now.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Do not hide errors or invalid states.
Stop when done.
```

`weighted + contrast`:

```text
Optimize for the smallest correct diff.
Read first, reuse existing code, then make the smallest readable change.
Verify the relevant behavior, then stop.

Read the existing code before editing; do not guess APIs, helpers, or patterns.
Use existing helpers and patterns before adding new code; do not duplicate helper logic.
Prefer the smallest readable change; do not rewrite nearby code just because you saw it.
Verify with the smallest relevant test; do not stop on an unverified change.

Build only what is needed now.
Use built-ins before adding dependencies.
Touch the fewest files needed.
Do not add abstractions for one-shot code.
Preserve existing behavior unless asked to change it.
Do not hide errors or invalid states.
Stop when done.
```

| experiment | correctness | gpt-5.5 | gpt-5.4 | mini | spark | files touched | patch size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weighted core | 93.75 | 87.50 | 100.00 | 100.00 | 87.50 | 1.41 | 22.84 lines |
| contrast boundaries | 96.88 | 100.00 | 87.50 | 100.00 | 100.00 | 1.69 | 26.53 lines |
| weighted + contrast | 93.75 | 100.00 | 100.00 | 100.00 | 75.00 | 1.47 | 22.66 lines |

## Reading The Result

The strongest context weighting produced the smallest average patch for stronger
models. It also hurt the weakest model.

That is the important signal. Stronger wording does not simply mean better
behavior. More pressure can shrink the diff, but it can also make weaker models
miss requirements or overfit the instruction to "be small."

The current 11-line `AGENT.md` stays as the default because it is the more
general tradeoff. It is not the smallest prompt in every slice, and it is not
trying to be. It is trying to pull agents toward smaller, more local diffs
without turning the instruction into a brittle task in itself.

## Practical Takeaway

Use prose rules to shape behavior. Use mechanical boundaries to enforce it.

For diff discipline, a short `AGENT.md` can help. For guarantees, use tests,
schemas, validators, sandboxes, permissions, CI, deterministic code, or human
review.
