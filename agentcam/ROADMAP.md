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

### 1. GitHub Action / GitLab CI plugin

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

**Timing.** Open. Suggestions and concrete use cases are welcome —
file an issue or email — and will be considered. No specific bar to
clear, no promise to build. Decision is mine.

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

### 2. Custom risk rules via YAML

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

### 3. `agentcam compare <run-id-a> <run-id-b>`

**What.** CLI subcommand to diff two run reports.

**Why.** "Did the second attempt actually fix the regression introduced
by the first?" Local-only, no network, no SaaS — fits v0.x boundary.

### 4. POSIX hardening

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

### 5. SARIF output

**What.** Optional `--format sarif` for risk flags.

**Why.** Lets enterprise security teams ingest agentcam output into their
existing SARIF-aware tooling (GitHub Code Scanning, Sonarqube). Cheap to
add; opens an enterprise door without changing the CLI's positioning.

---

## v0.3+ candidates (later)

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
