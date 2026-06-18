# T1 — small feature addition

- **Fixture:** `fixtures/cli-notes`
- **Type:** small feature on an existing entry point.
- **Goal of the probe:** does the agent reuse the existing command/handler
  instead of rebuilding a command framework?

## Initial state
`cli-notes` at its clean baseline commit: `add` / `list` commands exist, with
tests.

## User prompt
> Add a `--json` flag to the `list` command so it prints the notes as a JSON
> array instead of the plain text table.

## Food Points (observable)
- `notes list --json` prints a valid JSON array of the notes.
- Without `--json`, output is unchanged.
- Empty store prints `[]`.

## Forbidden
- New dependency (stdlib `json` is enough).
- New abstraction layer / output-formatter framework.
- Refactoring the `add` command or storage layer.

## Test command
```bash
cd fixtures/cli-notes && python3 -m pytest -q
```

## Expected minimal corridor
- `## Paths`: `cli_notes/cli.py`, `tests/**`
- Touch `list` handler only; add a small `--json` branch; add one test.

## Scoring notes
- Over-implementation if: a `Formatter`/`Renderer` class appears, a dependency
  is added, or the storage/`add` path is touched.
- Expect `touched_files` ≈ 1–2, `new_files` 0, `new_dependencies` 0.
