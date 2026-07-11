# Slime Coding concept

Slime Coding applies four collaboration ideas as one executable loop:

```text
necessary observable result
→ repository evidence
→ narrow intended paths
→ smallest sufficient change
→ final-state verification
```

The agent, not the user, turns the request into an outcome and a path boundary.
The boundary is stored in Git-local state before the first product edit. Hooks
then compare observable writes against it. The user sees only the final Stop
summary or, for high-risk work, one state-bound confirmation request.

This design follows three constraints:

1. Broad reading is cheap; unrequested writing is not.
2. Fewer lines are not better when they add hidden state or understanding cost.
3. A claim of completion matters only when checks and evidence describe the
   final product state.

The coordinator is a workflow guardrail, not an OS sandbox and not proof that a
design is good. It makes drift, missing tests, and high-risk changes visible
without asking the user to operate an internal methodology.
