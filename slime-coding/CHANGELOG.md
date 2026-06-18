# Changelog

All notable changes to Slime Coding are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project is installed by
cloning, so "versions" track the git history rather than published releases.

## [Unreleased]

### Added
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
- L3 report now includes `corridor changed this session: yes/no`, surfacing
  (without blocking) the fact that the `.slime/` bootstrap exemption lets a
  corridor be widened mid-task.
- `LICENSE` (MIT) and this changelog.
- `docs/CONCEPT.md`: the Slime Coding concept / methodology document (v0.2),
  linked from the README. The README stays the engineering/how-to layer.
- README concept illustration (`assets/slime-coding.png`).

### Changed
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

## [0.1.0] — initial

### Added
- Four-layer Slime Coding discipline: L0 `slime-navigate` skill +
  `CLAUDE.slime.md` template + `corridor.md`; L1 `PRUNED.md` injection with
  decay (`bin/prune-inject`); L2 git-fact gates and L3 cost report
  (`bin/patch-cost`); `/slime-corridor` and `/slime-prune` commands.
