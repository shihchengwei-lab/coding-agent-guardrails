# Changelog

All notable changes to Slime Coding are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project is installed by
cloning, so "versions" track the git history rather than published releases.

## [Unreleased]

### Removed
- `install.sh --with-cg <path>` and its coding-guidelines pairing path. The
  combined setup showed poor fit for Slime Coding's current goal: it tends to
  add testing wrappers and extra files in constrained agent benchmarks, reducing
  the "small diff" benefit. The regression test now asserts the flag is rejected.
- `experiments/` (fixtures, runners, score.py, slime-bench, runs), `reports/`
  (06-18 / 06-21 / 06-22 benchmarks), `docs/VALIDATION_PLAN.md`, and
  `tests/test-bench.sh`. The sandbox-benchmark approach could not measure
  effect-size on the "AI writes too much code" target — the fixtures were
  small enough that AI baseline behaviour was already minimal, so the matrix
  produced nulls that didn't isolate Slime's effect from the test's lack of
  pressure. The earlier reports' framings of those nulls as "Slime doesn't
  help" or "Slime adds cost" overstated what the cells supported. Rather than
  let them stand and mislead, the data and the reports are removed; the
  effect-size question is now handled by the public Ponytail-derived benchmark
  in `benchmark/`. The mechanism tests continue to cover the hooks directly.

### Added
- `bin/commit-evidence` plus Git `prepare-commit-msg` installation: commits can
  automatically carry a short Slime evidence block with corridor id, scope,
  semantic delta, allowed paths, staged touched files, out-of-corridor count,
  new dependencies, and verification. It is audit evidence, not a blocking
  gate, and install preserves any existing `prepare-commit-msg` hook.
- `SLIME_STRICT_CORRIDOR=0`: escape hatch that downgrades out-of-corridor
  product-code edits to report-only. The default is now strict: Stop blocks
  product-code edits outside the current corridor `## Paths`; `.slime/`
  artifacts and repo metadata stay exempt.
- `Semantic Delta` and `Non-goals` fields in the corridor template, slash
  command, and navigation guidance. They make each corridor name what behaviour
  is allowed to move and which APIs, data flow, naming, architecture, or
  ownership boundaries should stay still.
- L2 **typecheck gate** (`SLIME_TYPECHECK_CMD`, opt-in): at Stop, runs a type
  checker (e.g. `dart analyze`) as a contact sensor and blocks if it is red —
  catching hallucinated attachment points (a reference to a symbol/file/API
  that doesn't resolve). Unlike the failing-check gate it has no log-and-leave
  escape: unresolved code is broken, not an abandoned-but-logged design, so the
  only way out is to fix the reference or scope it as new work. Exit-code only
  (no output parsing, no multi-language adapter); degrades when unset / command
  not found / timeout. Behaviour tests AC1–AC6 in `tests/test.sh`. A
  mechanism, with no claim that it reduces hallucinations in practice.
- `install.sh`: clone-and-install flow. Wires the two hook scripts into a
  target project's `.claude/settings.json` (across SessionStart,
  UserPromptSubmit, PreToolUse, Stop) with a quoted absolute path, links the
  `slime-navigate` skill and the `/slime-corridor` / `/slime-prune` commands
  into `.claude/`, and seeds `.slime/` when absent. Idempotent; backs up
  `settings.json`.
- `hooks/hooks.template.json`: hook block with a `__SLIME_HOME__` placeholder
  for manual installers. Commands run via `python3`, so install does not
  depend on the clone keeping its executable bit.
- `tests/test.sh`: minimal behavioural tests for the hooks (corridor gate,
  bootstrap exemption, template rejection, env handling, Stop gates).
- GitHub Actions CI (`.github/workflows/ci.yml`): runs the tests, syntax/JSON
  checks, shell lint, executable-bit check, and an idempotent `install.sh`
  smoke test on push / PR to `main`. README shows a CI badge.
- Validation harness (`docs/VALIDATION_PLAN.md`, `experiments/`): `new-run.sh`
  to materialise a fixture as an isolated git repo, `metrics.py` for the
  git-derived run metrics, `schema/metrics.schema.json`, task cards T1–T8, and
  the `cli-notes` fixture. Phase A edge tests added to `tests/test.sh`
  (now 19 checks). Mechanism verification recorded in
  `reports/2026-06-18-mechanism-verification.md`. README states the
  experimental/validation status.
- `experiments/slime-bench`: controlled-benchmark runner (Python3 stdlib) that
  wraps the existing building blocks into five subcommands —
  `plan` / `new-cell` / `measure` / `validate` / `aggregate`. `new-cell`
  materialises a fixture and applies the per-condition stack (A/B/C/D in
  plan §6); `measure` invokes `metrics.py` and writes `metrics.json` into the
  cell; `validate` checks a record against `schema/metrics.schema.json`
  (required + type + enum + minimum); `aggregate` walks a runs root and
  prints a markdown table. The agent run itself stays out of scope — the
  runner only sets the stage and reads the diff.
- `tests/test-bench.sh`: behavioural tests for the runner (plan, new-cell
  across all four conditions, measure, validate, aggregate).
- L3 report now includes `corridor changed this session: yes/no`, surfacing
  (without blocking) the fact that the `.slime/` bootstrap exemption lets a
  corridor be widened mid-task.
- `LICENSE` (MIT) and this changelog.
- `docs/CONCEPT.md`: the Slime Coding concept / methodology document (v0.2),
  linked from the README. The README stays the engineering/how-to layer.
- README concept illustration (`assets/slime-coding.png`).

### Changed
- Out-of-corridor product-code edits now block by default at Stop. This makes
  "minimal semantic displacement" the default behaviour instead of an optional
  strict mode; set `SLIME_STRICT_CORRIDOR=0` to downgrade that check to
  report-only. The public benchmark rows for `slime-coding` were refreshed to
  the strict-corridor default run.
- Renamed the L2 "prune-logging" gate to what it actually enforces: a
  **failing-check-at-stop** gate. Its teeth are on the unambiguous git/exit
  fact "`SLIME_TEST_CMD` is red as you finish"; recording a path in `PRUNED.md`
  is just the acknowledgement that lets you stop on red (the other way out is to
  make the check pass). It never claimed to verify that you "pruned" anything —
  abandoning a design is not a git fact. Block message and `docs/DESIGN.md`
  updated; behaviour unchanged.
- `out-of-corridor` count (L3 report and `metrics.py`) now excludes `.slime/`
  artifacts: editing the corridor is tracked separately, and `PRUNED.md`
  updates are required, not scope creep.
- Dropped the Claude Code plugin format (removed `.claude-plugin/plugin.json`,
  renamed `hooks/hooks.json`). Installation is now clone + `install.sh`.
- Corridor gate (L2, PreToolUse) now blocks on invalid corridors, not just a
  missing file: a missing `# Corridor:` header, the template id
  `example-feature`, an empty `## Paths`, or the template example globs.
- The prune-logging block message now says "no uncommitted change relative to
  HEAD" instead of "not updated this session", matching the implementation.
- Docs clarify the prune-logging gate detects an uncommitted change versus
  `HEAD` (not a Claude Code session boundary), and that the L3 `systemMessage`
  report is user-facing by design.

### Fixed
- Bootstrap deadlock: the corridor gate now always allows writes under
  `.slime/`, so a corridor or `PRUNED.md` can be created when none exists yet.
- `prune-inject` no longer crashes on a non-numeric or negative
  `SLIME_PRUNE_RECENT` (falls back to `5`); `0` now means "no recency window"
  instead of injecting every record.
- `experiments/metrics.py`: force UTF-8 when capturing git output so the
  script runs on Windows shells whose default locale is not UTF-8 (e.g.
  cp950); behavior on Linux/macOS is unchanged.

## [0.1.0] — initial

### Added
- Four-layer Slime Coding discipline: L0 `slime-navigate` skill +
  `CLAUDE.slime.md` template + `corridor.md`; L1 `PRUNED.md` injection with
  decay (`bin/prune-inject`); L2 git-fact gates and L3 cost report
  (`bin/patch-cost`); `/slime-corridor` and `/slime-prune` commands.
