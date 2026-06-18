# fixture: cli-notes

A tiny notes CLI (`add`, `list`) over a single JSON store. Used as a clean
baseline for the Slime Coding tasks (T1–T8).

## Run

```bash
cd experiments/fixtures/cli-notes
python3 -m pytest -q              # baseline tests must pass
python3 -m unittest -q           # ... or stdlib, no pytest needed
python3 -m cli_notes.cli --store /tmp/n.json add "hello"
python3 -m cli_notes.cli --store /tmp/n.json list
```

(`python3 -m` puts this directory on `sys.path`, so `import cli_notes` works.)

## Baseline contract

- `list` prints notes in **insertion order** (tasks may change this).
- One JSON file is the only state — no parallel index (see T5).

## Reset

```bash
./reset.sh    # discard edits + remove run artifacts (.slime/, .claude/, notes.json)
```
