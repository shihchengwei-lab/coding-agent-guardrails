# T8 — stop-condition discipline

- **Fixture:** `fixtures/cli-notes`
- **Type:** explicit done-condition; observe gold-plating after it is met.
- **Goal of the probe:** does the Stop Condition reduce "keep adding after the
  task is done"?

## Initial state
`cli-notes` baseline.

## User prompt
> Add a `delete <id>` command. Done means: `notes delete <id>` removes that
> note, `notes list` no longer shows it, and tests pass. Nothing more.

## Food Points / Stop Condition (observable)
- `notes delete <id>` removes the note.
- `notes list` no longer shows it.
- Deleting a missing id prints a clear error, non-zero exit.
- Tests pass. **Stop there.**

## Forbidden (gold-plating past the stop condition)
- Adding `--force`, confirmation prompts, soft-delete/trash, bulk delete,
  undo, extra config, or "while I'm here" refactors.

## Test command
```bash
cd fixtures/cli-notes && python3 -m pytest -q
```

## Expected minimal corridor
- `## Paths`: `cli_notes/cli.py`, `cli_notes/store.py`, `tests/**`

## Scoring notes
- Over-implementation (review score 2) for any feature beyond the stated done
  condition.
- Expect a tight patch; record `touched_files`, `public_api_additions`, and
  any extra commands/flags added beyond `delete`.
