# Changelog

All notable changes to agentbox are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely.
Versioning follows [SemVer](https://semver.org/) once 1.0.0 ships;
0.x is unstable on purpose.

## [Unreleased]

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
  Repo: https://github.com/shihchengwei-lab/agent-run-flight-recorder

## [0.1.0] — 2026-05-16

First release. The whole point of v0.1 is "wrap one agent run, produce a
report, do not lie about what we don't know."

### Added

- **`agentbox version`** — print version and exit
- **`agentbox run -- <argv...>`** — wrap an argv-style command, record
  before/after git state, tee stdout/stderr, generate Markdown report

#### What gets recorded per run

- `stdout.log` / `stderr.log` — raw bytes from the subprocess, preserved
  for forensic review
- `stdout.redacted.log` / `stderr.redacted.log` — secrets stripped
  (best-effort) via streaming buffer (handles tokens cut at chunk
  boundaries and multi-line PEM blocks)
- `manifest.json` — machine-readable run metadata
- `AGENT_RUN_REPORT.md` — human-readable report

All artifacts live under `<git_dir>/agentbox/runs/<run_id>/` so git itself
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
