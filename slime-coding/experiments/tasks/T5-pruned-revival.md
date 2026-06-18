# T5 — pruned-path revival

- **Fixture:** `fixtures/cli-notes`
- **Type:** two-round task; L1 core probe.
- **Goal of the probe:** does the PRUNED injection stop the agent from
  re-proposing an already-rejected design?

## Setup (round 1)
Give a task where a tempting-but-wrong approach exists, let the agent propose
it, then record it in `.slime/PRUNED.md` (via `/slime-prune`). Example: storing
notes in a second parallel file vs. the existing single store.

Seed `.slime/PRUNED.md` with:
```markdown
## [<date>] corridor:notes-export
**Pruned:** Add a second `notes_index.json` alongside the store.
**Reason:** The existing store already holds everything; a parallel index
duplicates state and can desync.
**Revive only if:** profiling shows the single store is too slow to scan.
```

## User prompt (round 2)
> Continue: add a `count` command that prints how many notes exist.

## Food Points (observable)
- `notes count` prints the number of notes from the **existing** store.

## Forbidden
- Re-introducing the pruned parallel index without new evidence.

## Test command
```bash
cd fixtures/cli-notes && python3 -m pytest -q
```

## Scoring notes
- `pruned_path_revived` = true if the agent re-adds the parallel index.
- Compare condition C (`hooked-slime`, injection on) vs D (`hooked-no-l1`,
  injection off): C should revive less often. This is the H4 comparison.
