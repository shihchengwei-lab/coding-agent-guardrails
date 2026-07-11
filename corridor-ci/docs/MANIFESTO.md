# The Corridor Manifesto

Code is now cheap. Review is not.

A pull request costs minutes to generate and hours to review. The person
paying those hours needs enough information to decide whether to pay.

We are not against AI. We do not care who wrote the code. We care that
someone can say where the change was meant to stop.

Every low-context PR outsources the same three questions to the maintainer:

> Why does this exist?
> Where does it end?
> Where do I start reading?

Answering them by reading the diff is the most expensive possible way to
answer them.

Longer descriptions are not the fix. A vague PR and a verbose PR fail the
same way: nobody knows where the change was supposed to stop.

So we ask for a handoff. Five lines:

```md
Decision: #123
Scope: pkg/parser/*, tests/parser/*
Review first: pkg/parser/links.py
Verified: pytest tests/parser
Risk: none-detected
```

Thirty seconds for the author. It hands the maintainer the boundary instead
of hiding it in the diff.

The author's words explain intent. Recorded behavior determines confidence:
manual checks stay labeled manual, and a check is called local-recorded only
when the committed author-controlled observation matches it. Missing or
partial observation stays
visible instead of being promoted into proof.

An author who cannot fill in these five lines, no matter who they are, is
not ready to ask for review.

A red check does not mean the code is bad. It means information is missing.
Humans still review. The corridor only decides where review begins.

Tiny fixes stay exempt. This is not ceremony. It is the minimum unit of
respect for someone else's attention.

No scope, no review.
