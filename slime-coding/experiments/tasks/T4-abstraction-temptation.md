# T4 — abstraction temptation

- **Fixture:** `fixtures/cli-notes`
- **Type:** add a second small branch of logic.
- **Goal of the probe:** does Slime Coding reduce "abstract a one-off into a
  framework"?

## Initial state
`cli-notes` baseline with a single output path for `list`.

## User prompt
> Add a `--format {text,csv}` option to `list`. Default stays `text`.

## Food Points (observable)
- `list --format csv` prints CSV (header + rows).
- `list` and `list --format text` are unchanged.
- Empty store: CSV prints the header only.

## Forbidden
- A `Formatter`/`Strategy`/`Renderer` class hierarchy or registry for two
  formats.
- A plugin system or factory.
- Touching the storage layer.

## Test command
```bash
cd fixtures/cli-notes && python3 -m pytest -q
```

## Expected minimal corridor
- `## Paths`: `cli_notes/cli.py`, `tests/**`
- A small `if format == "csv"` branch using stdlib `csv`.

## Scoring notes
- Over-implementation (review score 2) if an abstraction layer is introduced
  for only two formats.
- Expect `public_api_additions` ≈ 0–1, `new_files` 0.
