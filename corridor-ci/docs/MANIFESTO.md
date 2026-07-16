# The Corridor Manifesto

Review attention is scarce. Before a maintainer reads a diff deeply, a tool
should answer four factual questions:

1. What product files changed?
2. Where did the agent intend the change to stop?
3. Which checks actually ran against the final state?
4. Which file should the reviewer inspect first?

Earlier Corridor versions made the author encode those answers in five exact PR
body lines. That exposed the right concerns but assigned machine bookkeeping to
the human. It also allowed prose, recorded evidence, and final state to drift
apart.

Corridor v15 moves that structure to `.guardrails/review.json`. The local Stop
coordinator generates it from Git-local intent, trusted checks, Agentcam, and
the final product fingerprint. CI recomputes the PR state independently. The PR
body is again for normal human explanation, with no fixed grammar.

The artifact is not a quality score or third-party attestation. It is
author-controlled evidence made falsifiable by state binding. A red Corridor
means the review facts are missing, stale, malformed, under-scoped, or
under-reporting objective risk; it does not mean the implementation is bad.

The useful boundary is simple:

> Humans explain why. Tools record what happened and prove which final state
> they are describing.

Required GitHub checks remain essential. A repository workflow is only a merge
gate when ruleset or branch protection makes it required, and PR policy must
run from the default branch so a change cannot replace its own enforcement.
