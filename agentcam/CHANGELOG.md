# Changelog

All notable changes to agentcam are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely.
Versioning follows [SemVer](https://semver.org/) once 1.0.0 ships;
0.x is unstable on purpose.

## [Unreleased]

### Added (2026-05-20, `RuleSet` substrate for custom risk rules)

- **`PathMatchers` and `RuleSet` dataclasses** in `scanner.py`. A
  `RuleSet` carries HIGH/MEDIUM path matchers (segments / prefixes /
  basenames / extensions — kept split to preserve the existing "one
  flag per matcher class per file" dedup semantic) plus HIGH/MEDIUM
  output patterns. Frozen + tuples throughout.
- **`scan_paths(changed, *, ruleset=None)` and
  `scan_output(text, *, stream_label, ruleset=None)`** now accept a
  ruleset; `None` falls back to `default_ruleset()` which returns the
  built-in singleton. cli.py / hooks.py are unchanged (default works).
- **Substrate for roadmap #4** (custom YAML risk rules). A YAML loader
  is the natural next step — it just needs to produce a `RuleSet` and
  pass it in. The data shapes and internal call sites are ready; the
  loader itself is not in this release.
- **Backward compat**: the legacy module-level constants
  (`HIGH_PATH_SEGMENTS`, `HIGH_OUTPUT_PATTERNS`, etc.) are kept as the
  inputs to `_BUILTIN_RULESET`; external code importing them keeps
  working.
- **+7 tests** in `tests/test_scanner.py` (`TestCustomRuleSet`):
  default singleton identity, builtin parity, custom segment/output
  rules, empty-ruleset disables rule-based flags, count parity vs
  legacy constants.
- See `docs/design.md` decision #27 for the full rationale (why split
  matcher classes, why ship substrate before the YAML loader, etc.).

### Added (2026-05-20, Dependency manifest probe)

- **`AGENT_RUN_REPORT.md` now has a "Dependency Changes" section** when
  a run touched `requirements.txt`, `pyproject.toml`, or
  `package.json`. Each entry lists kind (added / removed /
  version_changed), package name, and before/after version specs;
  grouped per `(ecosystem, manifest_path)`.
- **Multi-ecosystem parsers**:
  - pip `requirements.txt` (URL fragments like `#egg=name` survive —
    inline comments require whitespace before `#`, matching pip's own
    rule)
  - `pyproject.toml` PEP 621 (`[project.dependencies]` +
    `[project.optional-dependencies.<group>]`) and Poetry
    (`[tool.poetry.dependencies]`,
    `[tool.poetry.dev-dependencies]`,
    `[tool.poetry.group.<group>.dependencies]`)
  - npm `package.json` (`dependencies` + `devDependencies`)
- **URL credentials in version specs are scrubbed at the parser
  boundary** — `git+https://USER:TOKEN@host/r.git` becomes
  `git+https://<redacted-credential>@host/r.git` before the spec ever
  reaches `DependencyChange`, the report, or the manifest.
- **Non-main deps are namespaced** so a package in main + an
  extra/dev group with different specs doesn't silently overwrite —
  e.g. `pytest [optional.test]`, `jest [devDependencies]`.
- **Path safety**: `scan_dependencies` rejects `..` segments and
  absolute paths so the probe cannot be coaxed into reading outside
  the repo.
- **+57 tests** in `tests/test_dependency_probe.py`. Hook mode and
  wrap mode both run the probe.
- See `docs/design.md` decision #25 for the full rationale (vs-HEAD
  baseline, no Cargo/Go in v1, lockfile exclusion, etc.).

### Added (2026-05-20, `ReportBundle` aggregator)

- **`ReportBundle` dataclass** in `agentcam.models` consolidates the
  inputs every renderer needs (manifest + before/after `GitState` +
  risk_flags + dependency_changes) into a single value. Future
  renderers planned for v0.2+ (SARIF #7, PR-comment #3) will consume
  a Bundle, not a 5-arg positional call.
- **`render_report` accepts either form** — the preferred
  `render_report(bundle)` and the legacy
  `render_report(manifest, state_before, state_after, risk_flags,
  dependency_changes=None)` (kept so the existing test suite and any
  external callers don't need a big-bang rewrite).
- `cli.py` (wrap mode) and `hooks.py` (hook mode) now both build a
  Bundle and call `render_report(bundle)`.
- **Why a Bundle, not a full event-stream layer.** A
  producer→`record(event)`→reducer→view design was scoped but
  deliberately deferred: no current or planned consumer needs
  streaming. SARIF and PR-comment are batch consumers; both work fine
  off a Bundle. See decision #26.
- **+5 tests**: 3 parity / defaults / pass-through, 2 lock-in tests
  for the `frozen=True at structure level, lists mutable by
  convention` boundary.

### Added (2026-05-18, Hook mode -- "always record" without the wrapper)

- **`agentcam hook-session-start` / `agentcam hook-session-end`** --
  two new subcommands designed to be wired into Claude Code's
  `~/.claude/settings.json` SessionStart / SessionEnd hooks. Read the
  Claude Code hook payload JSON from stdin (`session_id`, `cwd`),
  snapshot git state at session start, compare at session end. Generate
  a report under `<git_dir>/agentcam/runs/<run_id>/` ONLY if there's a
  git-visible diff (same no-diff cleanup as the wrapping path).
- **No more `cr "task"` typing for Claude Code users.** Set up the
  hook once; every subsequent `claude` session records automatically.
  Stays on Pro/Max subscription billing (interactive Claude Code, not
  `claude -p`) so the 2026-06-15 Agent SDK billing change doesn't bite.
- Both hook commands exit 0 unconditionally -- Claude Code is never
  blocked, even on agentcam internal errors. All exceptions caught at
  the top level; stderr print is itself wrapped in try/except.
- Persistence:
  `<git_dir>/agentcam/sessions/<sanitized-session-id>/state_before.pickle`,
  written via `.tmp` + `os.replace` (atomic so SessionEnd can never
  read a half-written file). Cleaned up on SessionEnd whether or not a
  report is generated.
- **Duplicate SessionStart** (resume / clear / compact) preserves the
  first snapshot so changes made between duplicates don't silently
  disappear from the eventual report.
- Snapshot loading validates `schema_version`, dict shape, and the
  types of every field used downstream (`state` is `GitState`,
  `started_at` is `datetime`, etc.). Malformed snapshots are discarded
  with cleanup, not orphaned.
- 14 new e2e tests in `tests/test_hooks.py`.
- See README "Hook mode" section for the one-time settings.json
  snippet, and `docs/design.md` decision #24 for the full rationale.

### Known limitations of Hook mode (acceptable for ship)

- Sanitized session-id collision: two distinct raw IDs that sanitize
  to the same string (e.g. `session-1` vs `session.1`) would share a
  session dir. Real Claude Code session IDs are UUIDs, so this is
  theoretical. Documented in `docs/design.md` #24.
- Windows reserved names (`CON`, `PRN`, etc.): same theoretical risk;
  same UUID mitigation in practice.
- Hook mode has no stdout/stderr capture -- the hook can't read Claude
  Code's transcript. Report Logs section points to empty placeholder
  files. To be addressed via a `capture_mode: hook` manifest field in
  a future release.
- Concurrent SessionStart TOCTOU: two SessionStart processes racing
  could both pass the `state_file.exists()` check. Real-world Claude
  Code single-install is fine; robust fix (lock dir / O_EXCL) deferred.

### Hardening (2026-05-18, second Codex pass on the no-diff cleanup)

- **`--keep-empty` now actually skips the fingerprint hashing cost it
  claims to.** Previously the cost was always paid inside
  `collect_git_state`; the flag only disabled the `rmtree` call.
  Moved fingerprint computation into a standalone
  `compute_diff_fingerprint()` in `git_state.py`, called from `cli.py`
  only when `not args.keep_empty`.
- **Partial-`rmtree` failure handled.** Previously, if `rmtree`
  removed the run dir itself but failed on a child, the fall-through
  to normal report generation crashed with `FileNotFoundError` when
  `write_text` tried to write to the missing parent. Now we check
  whether the run dir still exists after the exception; if yes, fall
  through normally; if no, log and `return 0` cleanly (no report, but
  no crash).
- **`git ls-files` failure no longer silently collides across
  snapshots.** Previously a failed `git ls-files --others` returned
  `b""`; if it failed on both pre and post snapshots, fingerprints
  matched and false cleanup could fire. Now returns a per-call unique
  sentinel (returncode + random nonce) so the fingerprints can never
  match across a failure — cleanup is conservatively skipped, report
  kept.
- **Symlink-retarget and large-file caveats documented** in
  `docs/design.md` decision #23 as known limitations.

### Changed (2026-05-18, "always record, throw away if no diff")

- **No-diff success runs now auto-clean their run dir.** `agentcam run`
  compares pre/post git state (`head`, `porcelain`, full diff bytes,
  and untracked file contents); if identical AND the wrapped subprocess
  exited 0, the entire `<git_dir>/agentcam/runs/<run_id>/` is deleted
  and stderr prints `agentcam: no git-visible changes; report skipped`.
  Pure-alignment sessions (agent and user discussed without changing
  code) no longer clutter `runs/`.
- **Opt out with `--keep-empty`**: `agentcam run --keep-empty -- ...`
  preserves the old "always keep" behavior for any single invocation.
- **Soft breaking change** — anyone who relied on every wrapped run
  producing a report (e.g. an external script that scans
  `<git_dir>/agentcam/runs/` after every wrap) needs `--keep-empty` to
  maintain that.
- **Untracked file contents are hashed** as part of the pre/post state
  comparison so an in-place rewrite of a pre-existing untracked file
  is detected as a change. Caught by Codex adversarial review before
  ship — without it, the fingerprint would falsely match across the
  rewrite and the report would be wrongly deleted (data loss).
- **`shutil.rmtree` failure now falls through to normal report
  generation** instead of silently swallowing the error. On Windows,
  AV scanners or held file handles can make `rmtree` fail; with
  `ignore_errors=True` users would see "report skipped" while orphan
  logs remained on disk.
- See `docs/design.md` decision #23 for the full rationale.
- +8 regression tests (6 for the cleanup behaviors, 2 for the Codex
  edge cases). Test total: 171 → 179 on Windows (+1 POSIX-only skip).

### Documented (2026-05-16, from first dogfood session)

- **README known-limitations** now states the actual failure mode for
  wrapping interactive TUI agents (specifically Claude Code):
  `agentcam run -- claude` (no args) errors because claude refuses to
  open its TUI when stdout is not a TTY; `agentcam run -- claude "..."`
  and `agentcam run -- claude -p "..."` both work (claude switches to
  print mode when given a prompt + non-TTY). Previous wording ("may
  render imperfectly") understated this. True PTY-backed wrapping
  deferred to v0.2.

### Published to PyPI (2026-05-16)

- **`pip install agentcam` now works** — wheel + sdist uploaded to PyPI:
  <https://pypi.org/project/agentcam/0.1.0/>
- Owner: `shihchengwei` (PyPI account). Verified end-to-end: fresh venv
  → `pip install agentcam` → `agentcam version` returns `agentcam 0.1.0`.
- README install section updated (removed "Once published to PyPI" caveat).

### Renamed (2026-05-16)

- **Package + CLI renamed `agentbox` → `agentcam`** (PyPI name `agentbox`
  was taken; `agentcam` is available on PyPI and free of prominent GitHub
  collisions). Source dir `src/agentbox/` → `src/agentcam/`; CLI entry
  `agentbox` → `agentcam`; artifact path `<git_dir>/agentbox/runs/` →
  `<git_dir>/agentcam/runs/`. All 25 files updated; 171 tests still pass.
- GitHub repo renamed `agent-run-flight-recorder` → `agentcam`.
  Old URL auto-redirects via GitHub.

### Hardening (post-source-review fixes, 2026-05-16)

- **report.py**: `cf.rename_from` now passes through secret-like-filename
  redaction; `git diff --check` output now passes through a new
  `_redact_filenames_in_diff_check` helper; report `Logs` and
  `Local Artifacts` sections show paths relative to git_root instead of
  absolute (no longer leaks username + repo location).
- **redaction.py**: `StreamingRedactor` now keeps a 1024-char reserve on
  force-flush so a token straddling the SOFT_FLUSH boundary can reassemble;
  `feed()` strips NUL bytes after decode (catches UTF-16LE / NUL-interleaved
  output); added `URL_BASIC_AUTH` pattern to redact `https://user:pass@host`;
  all secret-like patterns now case-insensitive.
- **scanner.py**: secret-like basename patterns all case-insensitive
  (catches `.ENV`, `ID_RSA`, `.NPMRC` on case-insensitive filesystems).
- **runner.py**: `proc.wait()` wrapped in try/except KeyboardInterrupt /
  finally — Ctrl+C now escalates wait→terminate→kill and always joins tee
  threads (so logs flush). New `_escape_for_cmd_shim` helper caret-escapes
  `& | < > ^` and doubles `%` for the Windows `.cmd` / `.bat` shim path.
- **+21 regression tests** covering each fix.
- **External confirm-review**: Codex confirmed all 9 fixes OK with NO
  BLOCKERS (direct `codex exec`, after three attempts via the
  `codex-rescue` subagent forwarder hung in session deadlocks).
- **Cross-platform validation (partial)**: pytest now passes on Linux
  (WSL Ubuntu, Python 3.12.3) too — 172/172 (POSIX signal test runs there).
  Total coverage: Windows 171/172 + Linux 172/172. macOS still untested
  (no local hardware; CI yaml covers it pending future GH push).
- **POSIX risks documented for v0.2** (Codex cross-platform risk
  assessment): SIGINT process-group leak, non-UTF8 filename decoding,
  POSIX exec permission. See ROADMAP v0.2 "POSIX hardening" entry and
  `docs/design.md` caveat 3.
- **GitHub Actions matrix green (6/6 jobs)** on push to main:
  Linux / macOS / Windows × Python 3.11 / 3.12 all pass.
  Repo: https://github.com/shihchengwei-lab/agentcam (renamed from agent-run-flight-recorder on 2026-05-16)

## [0.1.0] — 2026-05-16

First release. The whole point of v0.1 is "wrap one agent run, produce a
report, do not lie about what we don't know."

### Added

- **`agentcam version`** — print version and exit
- **`agentcam run -- <argv...>`** — wrap an argv-style command, record
  before/after git state, tee stdout/stderr, generate Markdown report

#### What gets recorded per run

- `stdout.log` / `stderr.log` — raw bytes from the subprocess, preserved
  for forensic review
- `stdout.redacted.log` / `stderr.redacted.log` — secrets stripped
  (best-effort) via streaming buffer (handles tokens cut at chunk
  boundaries and multi-line PEM blocks)
- `manifest.json` — machine-readable run metadata
- `AGENT_RUN_REPORT.md` — human-readable report

All artifacts live under `<git_dir>/agentcam/runs/<run_id>/` so git itself
cannot stage them.

#### Risk heuristics in this release

- **HIGH**: tracked file deletions; sensitive path segments (`auth`,
  `login`, `oauth`, `session`, `jwt`, `permission`, `migration`, `secret`,
  `credential`, `terraform`, `kubernetes`, `helm`, etc.); sensitive
  basenames / extensions (`.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`,
  `schema.prisma`, `fly.toml`, `vercel.json`, `.tf`, `.tfvars`); GitHub
  Actions workflow paths; output-pattern hits like `git reset --hard`,
  `rm -rf /`, `chmod 777`, `curl ... | sh`, PowerShell
  `Remove-Item -Recurse -Force`, `Invoke-Expression`, conflict markers,
  `git push --force`.
- **MEDIUM**: dependency manifest changes (`package.json`, `pyproject.toml`,
  `Dockerfile`, etc.); output mentions of `tests failed`, `lint error`,
  `build failed`, `panic`, `segmentation fault`.
- No LOW level — filename-only heuristics for "trivial" changes are
  unreliable.

#### Redaction

- Streaming redactor handles tokens split across read chunks and PEM
  blocks split across multiple lines (PKCS#8 / RSA / EC / ED25519 /
  ENCRYPTED / OPENSSH).
- Secret-like filenames (`.env`, `*.pem`, `id_rsa`, `*credential*`,
  `*secret*`) are redacted in every Markdown surface (Changed Files, Risk
  Flags evidence, Diff Stat, Rollback Notes, Command field).
- Argv redaction also runs on each argv element (catches
  `--api-key sk-...` and `--config .env.production`).

#### Exit code

- Wrapper exits `0` iff subprocess returncode is `0`, `1` otherwise.
- Original returncode, platform, and a human interpretation (POSIX signal
  name; common Windows NTSTATUS like `STATUS_ACCESS_VIOLATION`) all go to
  `manifest.exit_detail` and the `Exit Code Detail` report section.
- Run-id collision (same millisecond, same slug, all hex retries
  exhausted) exits with `2` — distinct from "subprocess failed" `1`.

### Tests

- 159 unit + e2e tests across 8 test modules
- Cross-platform: passes on Windows (POSIX-only signal test skipped)
- e2e suite uses real subprocesses + real git repos via
  `tmp_git_repo` fixture
- Regression guards for every blocker found during two rounds of Codex
  adversarial review (PEM cross-chunk, exit-code 256-not-zero, segment vs.
  substring matching, staged-only diff visible, output evidence does not
  echo raw matched text, etc.)

### Documentation

- `README.md` — quick start, install, threat model, known limitations,
  hacking
- `docs/design.md` — 22 decisions in "decision / why / why not" format
- `examples/risky-auth-change/` — one committed sample report and scenario
  description
- `SECURITY.md` — vulnerability disclosure policy, scope, threat model

### Known limitations (v0.1)

- Not a sandbox; not a pre-execution gate; not a compliance product.
- Best-effort redaction; new secret formats may slip through.
- No interactive TUI rendering guarantee.
- No submodule / sparse-checkout special handling.
- Windows console encoding fallback may degrade live terminal display
  (raw log on disk is unaffected).
- `Tests / Build / Lint observed` always reports `unknown` — heuristic
  detection deferred to a future release.

### Out of scope (deliberately, see `docs/design.md` "Out-of-scope reminders")

- Sandbox / process isolation
- Pre-execution blocking / approval gating
- Auto-rollback / `git clean -fd` suggestions
- Cloud upload / telemetry of any kind
- VS Code / IDE integration
- GitHub App / GitHub Action (deferred to v0.2 if v0.1 finds users)
- Custom YAML risk rules
- Multi-run dashboard
- Hosted SaaS dashboard
