# Changelog

All notable changes to Slime Coding are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project is installed by
cloning, so "versions" track the git history rather than published releases.

## [Unreleased]

### Added
- `install.sh`: clone-and-install flow. Wires the three hooks into a target
  project's `.claude/settings.json` with a quoted absolute path, links the
  `slime-navigate` skill and the `/slime-corridor` / `/slime-prune` commands
  into `.claude/`, and seeds `.slime/` when absent. Idempotent; backs up
  `settings.json`.
- `hooks/hooks.template.json`: hook block with a `__SLIME_HOME__` placeholder
  for manual installers.
- `LICENSE` (MIT) and this changelog.

### Changed
- Dropped the Claude Code plugin format (removed `.claude-plugin/plugin.json`,
  renamed `hooks/hooks.json`). Installation is now clone + `install.sh`.
- Corridor gate (L2, PreToolUse) now blocks on invalid corridors, not just a
  missing file: a missing `# Corridor:` header, the template id
  `example-feature`, an empty `## Paths`, or the template example globs.
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
