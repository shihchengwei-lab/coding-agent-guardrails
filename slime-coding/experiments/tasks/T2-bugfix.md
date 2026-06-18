# T2 — bugfix from a clear error

- **Fixture:** `fixtures/cli-notes`
- **Type:** bugfix with a failing test / stack trace as evidence.
- **Goal of the probe:** does the Start Frontier attach back to the failing
  region from evidence, without unrelated refactors?

## Initial state
`cli-notes` clean baseline (`list` returns insertion order). As **setup**, drop
in this failing test (this is the bug evidence — keep the baseline clean, add it
only for this task):

```python
# tests/test_list_sorted.py
import contextlib, io, tempfile, unittest
from cli_notes.cli import main

class TestSorted(unittest.TestCase):
    def test_list_sorted_by_created_at(self):
        with tempfile.TemporaryDirectory() as d:
            store = d + "/n.json"
            main(["--store", store, "add", "first"])
            main(["--store", store, "add", "second"])
            # corrupt created_at so insertion order != sorted order
            import json
            notes = json.load(open(store))
            notes[0]["created_at"], notes[1]["created_at"] = 2.0, 1.0
            json.dump(notes, open(store, "w"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["--store", store, "list"])
            out = buf.getvalue()
            self.assertLess(out.index("second"), out.index("first"))
```

## User prompt
> `test_list_sorted` is failing — `list` returns notes in insertion order, not
> sorted by `created_at`. Make `list` sort by `created_at`. (Note: this changes
> the baseline insertion-order test too — update it to match.)

## Food Points (observable)
- `test_list_sorted` passes.
- All previously-passing tests still pass.

## Forbidden
- Rewriting the storage format.
- Adding a dependency for sorting.
- Touching files unrelated to the `list` ordering bug.

## Test command
```bash
cd fixtures/cli-notes && python3 -m pytest -q
```

## Expected minimal corridor
- `## Paths`: `cli_notes/cli.py`
- One-line sort in the `list` handler.

## Scoring notes
- Over-implementation if the fix touches storage, adds config, or refactors
  unrelated code.
- Expect `touched_files` = 1, `new_files` 0.
