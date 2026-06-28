# Roadmap

> Forward-looking. Subject to change. Anything here can be cut, rescheduled,
> or replaced based on what v0.1 users actually ask for.
>
> "Find users first, ship features second" is the rule. Do not build a
> feature on this list before there is at least one user requesting it.

## Why a roadmap exists

agentcam v0.1 is intentionally minimal. A roadmap is useful so that:

- Users can see what's likely vs. unlikely to be in v0.x.
- Contributors can see where help is welcome (and where the line is).
- Future-me can see what was deliberately deferred and why, instead of
  re-litigating decisions.

The product framing — **a local Git-aware flight recorder for AI coding
agent runs** — does not change. Anything that breaks that framing is out
of scope (see `docs/design.md` "Out-of-scope reminders").

---

## v0.2 candidates (next minor release)

Ordered by likely value to v0.1 users, **not** by build difficulty.

### Priority-6 surface batch — SHIPPED 2026-05-22

Six dogfood-driven gaps closed in one batch. Each entry is one commit
on `main`; see CHANGELOG `[Unreleased]` 2026-05-22 entries for the
detail and `docs/design.md` decisions #28-#31 for the rationale.

- **README network-visibility clarification.** "agentcam makes no
  network calls" now states it covers the agentcam process itself,
  not the wrapped agent / SDK / browser / shell / MCP client.
  Known-limitations bullet added. `docs/design.md` out-of-scope
  reminders pin the boundary.
- **Capture Visibility metadata** (`docs/design.md` #28). New
  `capture` block on `manifest.json` and `## Capture Visibility`
  table in `AGENT_RUN_REPORT.md`. Wrap mode declares
  `output_risk_scan = enabled`; hook mode declares
  `disabled_no_output_stream`, so "no output flag in hook mode"
  cannot be misread as "no risk happened".
- **Ruleset provenance** (`docs/design.md` #29). New `ruleset` block
  on every manifest + `## Scanner Ruleset` section on every report.
  Carries built-in id/version, custom-rules path/hash (null today),
  load_status, and a deterministic `merged_rules_sha256` over the
  effective rule set (declaration order + regex flags both included
  in the canonical form, per Codex review). Prerequisite for the
  YAML loader (#4 below) and for future `agentcam compare` (#5).
- **No-diff preservation when output risk visible**
  (`docs/design.md` #30). Wraps decision #23 with the natural
  exception: if the run produced no git-visible diff AND exited 0
  AND the output scanner flagged HIGH/MEDIUM patterns, the run dir
  is kept (`capture.empty_run_policy = "preserve_visible_risk"`).
  `--keep-empty` still wins; hook mode unchanged (no output stream
  to scan).
- **`agentcam export <run_id>`** (`docs/design.md` #31). New CLI
  subcommand producing a share-safe redacted ZIP bundle (report +
  redacted manifest + redacted logs + checksums + EXPORT_NOTES).
  Raw stdout/stderr excluded by default; `--include-raw` opt-in.
  Path-traversal defense in depth (regex screen + resolved-parent
  check). Atomic `.tmp + replace` write. No network calls.
- **Claude Code transcript ingestion now a v0.3+ candidate**
  (`ROADMAP.md` `v0.3+` section). Explicitly tracked with proposed
  scope and acceptance criteria, carrying local-only / redacted-only /
  non-blocking / no-LLM-summarization constraints.

Two external Codex review passes (the second after the first surfaced
fixes for the ruleset hash and the export checksum order). +50 new
tests in `tests/test_capture.py`, `tests/test_ruleset_provenance.py`,
`tests/test_export.py`, plus regression coverage in `test_e2e.py` and
`test_hooks.py`. Full suite 321 + 1 skip on Windows.

### Surface work — SHIPPED 2026-05-20

These don't have stand-alone user-visible feature names; they're
substrate that makes the items below cheaper to build (and that
landed in response to dogfood-driven gaps). See CHANGELOG and
`docs/design.md` decisions #25-27 for the full rationale.

- **Dependency manifest probe** (`docs/design.md` #25). New
  "## Dependency Changes" section in `AGENT_RUN_REPORT.md` when a
  run touched `requirements.txt`, `pyproject.toml`, or `package.json`.
  Multi-ecosystem parsers (pip / PEP 621 / Poetry / npm).
  URL-credential scrubbing at the parser boundary so
  `git+https://USER:TOKEN@host/...` never round-trips into the
  report. Path safety: rejects `..` and absolute paths in
  `scan_dependencies`. v1 covers Python + npm; Cargo / go.mod /
  lockfiles deliberately deferred.
- **`ReportBundle` aggregator + `write_run_artifacts` orchestrator**
  (`docs/design.md` #26). `ReportBundle` consolidates render inputs
  into one dataclass; `write_run_artifacts` is the shared post-run
  pipeline (probe → manifest → bundle → render → write) called from
  both wrap mode and hook mode. Any future renderer (SARIF #7,
  PR comment as part of #3) consumes a Bundle; any future
  orchestrator (PTY-backed #2) is a thin helper call site.
  Chose this over a full event-stream layer because no current
  consumer needs streaming.
- **`RuleSet` rule registry** (`docs/design.md` #27). `PathMatchers`
  and `RuleSet` dataclasses + `default_ruleset()` factory.
  `scan_paths` / `scan_output` take an optional `ruleset=` kwarg
  (defaults to built-in). Substrate for item #4 below — the YAML
  loader just needs to produce a `RuleSet` and pass it in; no
  scanner-internals churn required.
- **Hook-mode orphan cleanup** (CHANGELOG `Hardening 2026-05-20`).
  Any exception between `create_run_dir` and the report write now
  removes the half-built run dir AND the session dir, so repeated
  SessionEnd failures don't accumulate stale artifacts. Hook still
  exits 0 unconditionally.

### 1. Always-on recording (Claude Code via hooks) — SHIPPED 2026-05-18

**Status.** Shipped in the [Unreleased] section of CHANGELOG.md (will
be promoted to a tagged 0.2 release later). Implementation in
`src/agentcam/hooks.py`. Uses Claude Code's SessionStart / SessionEnd
hook events (not UserPromptSubmit / Stop — those are per-turn rather
than per-session; session-level captures more useful diffs). User
wiring: see README "Hook mode" section for the one-time
`~/.claude/settings.json` snippet.

**What.** A `settings.json` integration that runs agentcam automatically
from inside every Claude Code session — no manual `cr "task"` wrapper.
Uses Claude Code's SessionStart / SessionEnd hooks to snapshot git
state before and generate the run report after.

**Why first.** v0.1's opt-in wrapping (`cr "task"`) forces the user to
remember a command per invocation. Forget once = no record. The
flight-recorder framing requires always-on; opt-in undermines it.
Anthropic's 2026-06-15 billing change also moves `claude -p` (the headless
mode the current `cr` wrapper uses) off Pro/Max subscription onto a
separate Agent SDK credit pool — making the wrapped path both inconvenient
*and* costly while bare interactive `claude` stays free under
subscription. Hook mode is the smallest fix that records bare interactive
sessions, on subscription billing, with zero manual command.

**Vendor scope.** Claude Code only. For all other agents (Codex,
OpenHands, Aider), the existing wrapping path and the PTY entry below
cover always-on. agentcam's vendor-agnostic positioning is preserved by
keeping wrapping as the core mechanism — this is an accelerator on top,
not a replacement.

**Free or paid.** Free / OSS.

**Timing.** Open. File an issue or email with a concrete use case;
it'll be considered.

**Acceptance criteria (when built).**
- Owner can install agentcam, register the Claude Code hook once, and
  have every subsequent `claude` session auto-recorded without typing
  any agentcam command.
- "No-diff" runs (pre and post git state identical) are auto-discarded
  or not created — no point keeping zero-change recordings.
- Existing `agentcam run -- ...` wrapping path still works unchanged.
  Hook mode is additive, not a replacement.

### 2. PTY-backed wrapping — SHIPPED 2026-06-28 (v0.2.0 on PyPI)

Both backends shipped as a 7-commit batch in CHANGELOG.md `[0.2.0]`
section, tagged `v0.2.0` on GitHub, released to PyPI.
Implementation in `src/agentcam/runner.py`: `_run_pipe`,
`_run_pty_posix` (standard-library `pty.openpty`), `_run_pty_windows`
(pywinpty + ConPTY). Dispatched via the new `--backend` flag on
`cli.py`; default changed from implicit pipe to `pty` (auto-picks per
platform).

**What.** Replaced agentcam's PIPE-only stdio with PTY-backed
wrapping. Lets `agentcam run -- claude` and `agentcam run -- codex`
(bare, interactive) work — TUI renders, agentcam still records what
happened.

**Acceptance (as shipped).**
- ✓ `agentcam run -- claude` (no `-p`, no positional prompt) works
  on Windows: TUI rendered, keystrokes including Enter delivered,
  output captured to `stdout.log`, run report generated. **Owner
  manual-verified.**
- ✓ Same for `agentcam run -- codex` on Windows (npm `.cmd` shim
  path; wrapped via `cmd.exe /c` since pywinpty has no
  `shell=True`).
- ✓ Windows + macOS + Linux all pass CI on the dispatch + capture
  metadata + non-interactive PTY paths (echo / sys.exit / piped
  stdin via Python child).
- ✓ Existing `PIPE` path remains available via `--backend pipe`.
- ⚠ POSIX bare interactive TUI agents (Aider, OpenHands, real
  POSIX claude/codex) NOT implementation-verified — owner is on
  Windows. CI covers the structural PTY path but not real TUI
  agent rendering on POSIX.

See CHANGELOG `[Unreleased]` 2026-06-28 entry for full detail and
`docs/design.md` decision #32 for the rationale.

### 3. GitHub Action / GitLab CI plugin

**What.** A reusable CI step:

```yaml
- uses: shihchengwei-lab/agentcam-action@v1
  with:
    command: claude -p "fix the failing tests"
    attach-to-pr: true
```

**Why first.** Turns a local report into team workflow. The first
plausible *paid* feature (hosted PR dashboard / aggregation) builds on
this surface. CI integration is also the smallest possible team-tool
hook: no SSO, no DPA, no hosted infra needed.

**Free or paid.** The Action itself is free / OSS. Aggregating multiple
PRs across an org will be paid.

**Status (recorded 2026-05-16).** Suggested mid-launch by GPT/Codex
review; user decided to defer (decision logged here). Reasoning:
v0.1 has 0 real users yet, the "1 user requesting it" rule from the
ROADMAP intro applies. Building a team-workflow feature before having
individual-tool users would be premature.

**Timing.** Open. File an issue or email with a concrete use case;
it'll be considered.

**Acceptance criteria (when built).** v0.2.0 must:
- Publish `shihchengwei-lab/agentcam-action@v1` on GitHub Marketplace.
- Wrap an agent command (claude / codex / any argv) in CI.
- Post `AGENT_RUN_REPORT.md` as a PR comment when running in PR context.
  Handle the 65 535-char PR comment limit (truncate body, link to the
  full artifact).
- Upload the full run directory as a workflow artifact.
- Skip the PR comment step gracefully when running on `push` to a
  branch (no PR yet); just upload artifact in that case.
- Example workflow shipped at `examples/github-action/workflow.yml`
  with a one-page README explaining how to copy/adapt.
- No `attach-to-pr: true` requires any agentcam config or new schema
  field beyond standard GitHub Action inputs.

**Out of scope for v0.2 even if built.** Marketplace icon / branded
listing polish, multi-PR aggregation dashboard (those belong in a
paid SKU), GitLab CI (different platform, separate v0.3+ effort).

### 4. Custom risk rules via YAML

**What.** Users add their own path / output patterns:

```yaml
# .agentcam/rules.yaml
high_paths:
  - segment: payment
    label: payment processing path
  - basename: prisma.schema
    label: ORM schema
```

**Why second.** Repeated user request is "I have a sensitive area you
don't know about." Without YAML, every team forks the source.

**Constraint.** Basic rule mechanism stays free. Pre-built rule packs (PCI
patterns, HIPAA patterns, FinTech patterns) could be paid.

**Status (substrate SHIPPED 2026-05-20 + 2026-05-22).** Two layers
landed:
- 2026-05-20: the `RuleSet` data structure and the
  `scan_paths(ruleset=...)` / `scan_output(ruleset=...)` plumbing
  (see "Surface work" above).
- 2026-05-22: ruleset provenance — `merged_rules_sha256` over the
  effective rule set, `custom_rules_path` / `custom_rules_sha256`
  slots already on every manifest with null today, `load_status`
  ready to flip from `"builtin_only"` to `"custom_loaded"`. So a
  YAML-loaded rule set will show up in every report's
  `## Scanner Ruleset` section with no further manifest-schema
  churn.

What's left to ship: the YAML loader that reads `.agentcam/rules.yaml`,
merges user rules with the built-in default, builds a sibling
`provenance_for_custom_ruleset(...)`, and passes both through cli.py /
hooks.py. Estimated ~20 lines + tests; see `docs/design.md` #27 + #29.

### 5. `agentcam compare <run-id-a> <run-id-b>`

**What.** CLI subcommand to diff two run reports.

**Why.** "Did the second attempt actually fix the regression introduced
by the first?" Local-only, no network, no SaaS — fits v0.x boundary.

### 6. POSIX hardening

Three Codex-identified POSIX concerns the current code doesn't fully cover
(see `docs/design.md` caveat 3 for the full discussion):

- **SIGINT process-group cleanup**: `run_wrapped` only kills the direct
  child via `proc.terminate()` / `proc.kill()`. On POSIX, when wrapping
  `bash -lc "..."`, the wrapped script's own children (grandchildren of
  agentcam) survive the wrapper's SIGINT path. Fix: `subprocess.Popen(..., start_new_session=True)` on POSIX + `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` in the interrupt handler.
- **Non-UTF8 filenames in git porcelain**: POSIX paths are byte strings,
  not Unicode. `parse_porcelain_v1z` and `_git_text` decode with
  `errors="replace"`, which silently corrupts non-UTF8 paths before
  scanner / redaction sees them. Fix: `errors="surrogateescape"` for
  filenames, or byte-preserving path handling end-to-end.
- **POSIX exec permission / shebang**: Unlike Windows `.cmd` / `.bat`
  shims, POSIX scripts need the `+x` bit and a valid shebang. `resolve_command` doesn't check; failure mode is "command found but
  subprocess fails with ENOEXEC". Mitigation: add a pre-flight check or
  catch and re-message.

### 7. SARIF output

**What.** Optional `--format sarif` for risk flags.

**Why.** Lets enterprise security teams ingest agentcam output into their
existing SARIF-aware tooling (GitHub Code Scanning, Sonarqube). Cheap to
add; opens an enterprise door without changing the CLI's positioning.

---

## v0.3+ candidates (later)

### Claude Code transcript ingestion for hook mode

**What.** Parse Claude Code's `transcript_path` from the SessionStart /
SessionEnd hook payload and produce a local, redacted, best-effort
transcript-derived evidence summary for hook-mode reports. The
existing 2026-05-22 `capture` block already records
`transcript = "available_not_ingested"` when Claude exposes the path;
this entry is the next step — actually reading it.

**Why.** Hook mode cannot capture Claude Code's stdout/stderr (no
terminal output reaches the hook subprocess). Transcript ingestion is
the only currently documented path toward richer hook-mode visibility
without blocking Claude Code or replacing the user-facing TUI. PTY-
backed wrapping (v0.2 item #2) addresses the same gap for *other*
agents but does not help Claude hook-mode users — they're not using
the wrap path at all.

**Free or paid.** Free / OSS. The parser is small; risk-rule packs
built on top would be the paid layer (consistent with #4).

**Timing.** Open. File an issue with a concrete use case (e.g. "I want
to see which files my Claude session asked to read, even when no diff
landed"); it'll be considered.

**Proposed scope.**

- Best-effort JSONL parser (Claude Code transcript format)
- Local-only — agentcam never copies the transcript file
- Redacted output only by default; raw transcript text never enters
  the report
- Tolerate missing / unreadable / changed transcript format —
  parser failure must not block Claude Code and must not prevent
  git-diff report generation
- Report ingestion status in the existing `capture.transcript` field
  (flips from `"available_not_ingested"` to `"ingested_redacted"`)
- No upload, no aggregation, no LLM summarization

**Acceptance criteria (when built).**

- Hook mode reads `transcript_path` if present and parseable.
- Missing / inaccessible / malformed transcript degrades to
  `capture.transcript = "unknown"` (or stays at
  `"available_not_ingested"` if the parse was attempted and skipped);
  never a hard failure.
- Parser failure does not block Claude Code (hook still exits 0) and
  does not prevent the existing git-diff report from generating.
- Report shows transcript ingestion status in the Capture Visibility
  section.
- Raw transcript is not copied into `runs/<run_id>/` by default.
- Any derived transcript evidence passes through the existing
  redaction pipeline.
- Tests cover: missing transcript path, malformed JSONL, oversized
  file, basic valid transcript, redaction of secret-shaped content
  inside a transcript line.

**Out of scope for this entry even if built.** Per-turn report (one
report per user prompt — UserPromptSubmit vs SessionStart, see
`docs/design.md` §24), full event-stream layer, tool-call
reconstruction claims, file-read reconstruction claims, model-call
reconstruction claims, LLM-based summarization of transcript text.

### 5. Heuristic verification (`Tests observed`, `Build observed`, `Lint observed`)

Currently always `unknown` (`docs/design.md` § 9). Could be done by parsing
known formats (JUnit XML, ESLint JSON, Cargo test output) when present at
known locations. Will probably stay opt-in via flag.

### 6. Multi-run dashboard

Local-first first: a `agentcam view` command that renders the run history
as static HTML. No server required.

A hosted version (with auth + retention + search) is the natural paid
SKU, but it implies SOC2-style obligations — only after several teams
explicitly ask.

### 7. Slack / SIEM webhook output

Optional `--notify <webhook-url>` that sends a redacted summary on HIGH
flags. Off by default. Useful for teams that want notifications without a
hosted dashboard.

---

## What we deliberately are NOT doing (and why)

These are out of scope for the foreseeable future. If you want them,
agentcam is the wrong tool — see the alternatives noted.

### Sandbox / pre-execution blocking

agentcam is a recorder, not a gate. Pre-execution gating requires a
trustworthy runtime sandbox, a policy language, an approval UI, and
auditable rule evaluation. Each of those is its own product. We also
explicitly do not want to be in the position of "agentcam said it was
safe" — see the `docs/design.md` § 14–16 cluster.

### Auto-rollback

We will never run `git clean -fd` for the user, never `git reset --hard`,
never `git revert` automatically. The Rollback Notes section in the
report tells the user what they could run; the user runs it.

### Hosted SaaS dashboard (default-on)

Maybe eventually as a paid SKU, opt-in only. The local-only / no-telemetry
default is part of the product. Anything that defaults to uploading agent
runs anywhere is a different product.

### LLM-based risk analysis

"Send the diff to GPT-5 to judge if it's risky" is a different product.
agentcam is heuristic on purpose: cheap, deterministic, offline,
debuggable.

### IDE / VS Code extension

Probably never. The CLI is the unit of value. If someone wants an IDE
button that runs `agentcam run -- ...`, they can add it themselves in
two lines of `tasks.json`.

### Compliance / SOC2 evidence pipeline

Not the product. The Markdown report is for the developer reviewing the
PR, not for a compliance auditor. We will not add features that imply
the report is suitable as audit evidence.

---

## Pricing model (planning, not committed)

When (if) there is a paid tier, the shape is likely:

- **CLI**: free, MIT, runs entirely on the user's machine.
- **Team plan** (per-org subscription, not per-seat, not per-run):
  hosted PR comment integration, multi-run search, retention, SSO,
  audit log of who accessed which report.
- **Enterprise**: self-hostable team plan + SLA + DPA + signed contract.

What we will not charge for:

- The CLI itself
- Local report generation
- The risk pattern lists shipped in v0.1
- Reading or producing reports

What we might charge for:

- Multi-run aggregation across a team / org
- Long-term retention
- PR comment automation
- Pre-built compliance-flavored rule packs
- SSO / SAML / SCIM
- Audit log of report access

Per-run pricing is explicitly off the table — it would punish the exact
behavior (wrap every agent run) that the tool exists to encourage.

---

## How to influence this list

If you actually use agentcam, your input outweighs anything written here.

- File a GitHub issue with the use case.
- Email `shihchengwei@gmail.com` if it's sensitive.
- Pull requests that match the product framing are welcome; ones that
  break it (sandbox, auto-rollback, telemetry) will be politely declined
  with a link to `docs/design.md`.
