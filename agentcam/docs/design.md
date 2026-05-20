# agentcam v0.1 design notes

> Decision log for the next agent (or human) who picks up this codebase.
> Each section follows: **Decision** → **Why** → **Why not the alternative**.
> If you're about to change one of these, read the "Why not" first — that's
> usually the trap that was already considered and avoided.

This is a single file by design. Splitting into `risk-rules.md` and
`report-format.md` was considered and rejected: drift risk is high and the
narrative ties the rules to their motivations.

---

## 1. Output location: `<git_dir>/agentcam/runs/<run_id>/`

**Decision.** All run artifacts (raw logs, redacted logs, manifest, report)
go under `<git_dir>/agentcam/runs/<run_id>/`. We resolve `git_dir` via
`git rev-parse --git-dir`, so worktrees and submodule gitlink files work.

**Why.** Git does not track its own internals, so `git add .` (run by an
agent or human, by accident or intent) cannot stage these files. Safety is a
structural property, not a property of "remembering to add to .gitignore."

**Why not `.agentcam/runs/`** (in the repo root). It would require us to
either auto-edit the user's `.gitignore` (forbidden by user policy) or
trust the user to do it. If the user forgets even once, an agent that runs
`git add . && git commit && git push` will publish raw logs to GitHub. The
risk surface is too large for the convenience (shorter paths) it buys.

**Why not user cache** (`~/.cache/agentcam/<repo>/`). Decouples runs from
the repo, which is the wrong direction: a run *is about* this repo. Also
makes share/demo flow worse for non-engineering users.

---

## 2. Raw + redacted logs both kept; report only links to redacted

**Decision.** Each run produces `stdout.log` + `stderr.log` (raw) and
`stdout.redacted.log` + `stderr.redacted.log` (redacted). The Markdown
report only links to the redacted versions.

**Why.** The product framing is "flight recorder" — the value proposition
is a complete forensic record. If redaction misses a secret, the raw log is
the only way to find out *what* was missed. Cutting raw means "we redacted,
but if redaction was wrong, you'll never know."

**Why not redacted-only.** Reduces blast radius if the entire run dir is
shared, but breaks the forensic story.

**Caveat that must be in README.** Raw logs live on disk under `.git/`.
They will *not* be picked up by `git push`, but they *will* be picked up by:
cloud sync (OneDrive, Dropbox, iCloud Drive), system backups (Time Machine,
Windows File History), and zipping the entire repo for sharing. Users need
to know.

---

## 3. Tee uses dedicated threads — not select / asyncio / PTY

**Decision.** `runner.py._TeeThread`: one thread per pipe, each runs
`os.read(pipe.fileno(), 4096)` in a loop, writes raw bytes to a file, and
forwards bytes to the parent terminal. Redaction is *not* done in this
layer (see §6).

**Why.** Threads handle stdout and stderr concurrently with no risk of
back-pressure deadlock. Works identically on POSIX and Windows. The two
files have separate file handles, so writes don't interleave.

**Why not `select` / `selectors`.** POSIX `select` does not work on Windows
pipes. `selectors` has the same limitation.

**Why not `asyncio`.** Adds complexity for no benefit. We just need
"two streams in parallel," which threads do trivially. asyncio would also
fight with subprocess for pipe ownership.

**Why not PTY.** Windows stdlib has no PTY. We accept that interactive TUI
agents (curses-style, full-screen redraws) will not render perfectly. The
README says so.

**Windows console fallback.** When `sys.stdout.buffer.write(chunk)` raises
`OSError` or `UnicodeEncodeError` (cp950, cp1252 don't accept arbitrary
bytes), we fall back to `decode('utf-8', errors='replace')` and set
`manifest.terminal_forward_degraded = true`. Raw log on disk is unaffected.

---

## 4. argv-only — no shell language compatibility

**Decision.** `agentcam run -- <argv>` runs the subprocess with
`shell=False`. We do not interpret pipes (`|`), redirects (`>`), `&&`, or
variable expansion. If the user wants those, they wrap their own shell:
`agentcam run -- bash -lc "..."` / `pwsh -Command "..."` / `cmd /c "..."`.

**Why.** "Support any shell command" sounds nice but is a lie. Different
shells (bash, zsh, fish, pwsh, cmd) have different syntax; we cannot
implement compatibility correctly. argv is unambiguous.

**Why not `shell=True`.** Hands the user's command to whatever shell the
platform decides on. On Windows that's `cmd.exe` with surprising quoting.
Also opens shell-injection risk if a future version ever takes input from
config.

**Windows `.cmd` / `.bat` shim is a documented exception.** Many real CLIs
on Windows ship as `something.cmd` (e.g. `npm.cmd`, `codex.cmd`). These
files cannot be run by `CreateProcess` directly; they need `cmd.exe`. So
when `shutil.which` resolves to a `.cmd` or `.bat`, we set `shell=True`
*just for that invocation* and pre-quote the argv with
`subprocess.list2cmdline`. `manifest.shell_used` records which path was
taken.

---

## 5. Git state via `porcelain=v1 -z` + cached / non-cached diff doubles

**Decision.** Pre- and post-run state both run:
`git status --porcelain=v1 -z` (primary), plus `git diff [--cached] --stat`,
`git diff [--cached] --name-status`, and (post-run only)
`git diff [--cached] --check`.

**Why.** Porcelain v1 -z is the only output that:
- distinguishes staged / unstaged / untracked / renamed / unmerged
- handles filenames with spaces or non-ASCII (NUL-terminated)
- is stable across git versions

**Why both `--cached` and non-cached for diff.** `git diff --stat` *only
shows unstaged*. Without `--cached`, an agent that runs `git add .` would
have a fully blank Diff Stat section in the report. Two passes solve it.

**Why not just porcelain.** Porcelain doesn't render line-count diffs the
way humans expect. The diff stats are presentation only; porcelain remains
the source of truth for the changed-files list.

---

## 6. Redaction uses streaming buffer model (not chunk-internal regex)

**Decision.** `redaction.StreamingRedactor` keeps a sliding `pending`
buffer. On each `feed(chunk)`, it:
1. collapses *complete* PEM blocks (BEGIN..END) to `[REDACTED:PEM]`
2. if a BEGIN is seen without a matching END, holds everything from BEGIN
   onward (up to a 64 KB hard limit) waiting for END
3. for the rest, applies inline regex to *complete lines only* and emits;
   the trailing partial line stays in `pending`
4. on `close()`, flushes residue with one final scan

**Why.** Without a buffer, a token cut at chunk boundary leaks
(`ghp_AAAA…` arrives split, neither half matches by itself, both halves
get written through). PEM blocks span multiple lines, so per-line regex
also misses them.

**PEM regex shape.** `BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY` — the optional
prefix covers RSA / EC / ED25519 / ENCRYPTED / OPENSSH and PKCS#8 (which
has no prefix at all). The original plan wrote `[A-Z ]+`, which silently
fails to match PKCS#8. test caught it on first run.

**Why best-effort.** We do not promise to catch every secret. Documented in
README. The fallback is the raw log on disk: missed-by-redaction secrets
are still discoverable forensically, just not blocked.

---

## 7. Path matching uses segments, not substring

**Decision.** `scanner.path_matches_segment` matches if the segment is
exactly any directory or basename in the path, OR if a basename starts
with `<segment>.` or `<segment>-`. Examples for segment `auth`:

| Path | Match? |
|---|---|
| `src/auth/login.py` | yes (segment) |
| `auth.ts` | yes (basename `auth.X`) |
| `auth-helper.js` | yes (basename `auth-X`) |
| `src/author.md` | **no** |
| `src/authorization-docs/x.md` | **no** |

**Why.** Substring matching produces noise that erodes trust. Once a user
sees one obviously-wrong HIGH flag (e.g. `author.md` flagged as auth), they
start ignoring all flags. False positives are worse than false negatives
for a tool whose entire job is "tell me what to look at."

**Why not full glob / regex per rule.** Glob would work but adds a config
surface (now we'd need to spec the glob dialect, document it, test it).
Segment matching is one paragraph of code and one regex, and it covers the
intent.

---

## 8. Two risk levels (HIGH, MEDIUM) — no LOW

**Decision.** Risk levels are HIGH and MEDIUM only. There is no LOW.

**Why.** "LOW" was specced as "formatting / comment-only / docs-only."
Detecting that from filename alone is unreliable: a `.md` change might be
adding production credentials in a code block, and a `.py` change might be
a docstring typo. Producing LOW flags from filename heuristics would be
falsely precise.

**Verdict in report when there are no flags.** "LOW (no risk flags)" — this
is a phrasing choice, not a third level. The `RiskLevel` type literally
has no `LOW` member.

---

## 9. "Tests / Build / Lint observed" stays `unknown` in v0.1

**Decision.** The Verification section in the report always reports
`unknown` for these three checks in v0.1.

**Why.** Detecting "did the agent run tests?" via stdout heuristics
("PASSED" / "OK" / coverage tables) is too easy to fool and too easy to
miss. False reassurance ("all tests passed") is worse than no signal at
all. Reserved for v0.2 or later, when there's a real plan (e.g. parse
JUnit XML from a known location).

---

## 10. Never auto-edit user's `.gitignore`

**Decision.** agentcam does not touch the user's `.gitignore`. Period.

**Why.** "agentcam modified my repo configuration" is exactly the
behavior the tool is supposed to *detect*. We can't be the kind of tool we
warn about.

**Why this is OK.** Output goes under `.git/agentcam/`, which git ignores
natively (it ignores everything inside `.git`). So there is no
self-pollution problem to solve, and no need for `.gitignore`. Verified by
`test_e2e.TestSmoke.test_git_status_does_not_list_agentcam`.

---

## 11. Run ID: `YYYYMMDD-HHMMSS-<ms>-<slug>[-<hex>]`

**Decision.** Run id format includes milliseconds. Directory creation uses
`os.makedirs(exist_ok=False)` and retries up to 3 times with a fresh 4-char
hex suffix on collision. Three failed retries raise `RunIdCollisionError`,
which the CLI maps to **exit 2** (distinct from "subprocess failed" = 1).

**Why milliseconds.** Without them, two runs in the same second collide.
Two runs in the same millisecond is rare but real (parallel CI jobs, fast
scripts).

**Why exclusive `mkdir`.** Race-safe. The OS guarantees only one caller
sees success. Retry adds the hex suffix for defense in depth.

**Why exit 2 (not 1) for collision.** Exit 1 means "wrapped subprocess
failed." Exit 2 means "agentcam itself couldn't run." Distinguishing them
matters for CI users who treat `exit != 0` as "deploy failed."

---

## 12. Secret-like filenames are redacted in *every* markdown surface

**Decision.** A filename matching the secret-like pattern (`scanner.is_secret_like_filename`)
is replaced with `<redacted-secret-filename>` in:
- Changed Files table
- Risk Flags evidence
- Diff Stat (`git diff --stat` / `--name-status`)
- Rollback Notes (untracked file list)

The original filename appears only in `manifest.json` (forensic record) and
in the raw `git status` output written to disk under `.git/`.

**Why.** A filename can *be* a secret. `.env.production`, `aws-prod-key.pem`,
`id_rsa.bak.2024` — the name leaks the existence and identity of a
credential. If we redact only *contents* and leave names alone, we leak
half the secret.

**Pattern is intentionally broad.** It catches `*.pem`, `id_rsa*`, anything
containing `credential` or `secret` (case-insensitive), `.npmrc`, `.pypirc`,
etc. Substring match for `secret` / `credential` produces false positives
on docs files like `README-credentials.md`. This is acceptable: the cost of
a false positive is a wrong filename in a Markdown table; the cost of a
false negative is a leaked credential name in a shared report.

---

## 13. Command argv is also a secret surface

**Decision.** `redact_argv` runs `redact_text` *and* a secret-like
filename pattern over each argv element. The Markdown `Command:` field
uses the redacted version; `manifest.command_argv_raw` keeps the original.

**Why.** `agentcam run -- claude --api-key sk-…` is plausible. Without
argv redaction, the API key would land in `Command:` and stay there forever.
Same logic for `agentcam run -- vim .env.production` — the filename leaks.

**Why keep raw in manifest.** Forensic completeness. The user opted in by
writing it. Manifest stays under `.git/`, so it's not at the same exposure
risk as the markdown report (which gets shared, screenshotted, pasted to
issues).

---

## 14. Wrapper exit code is binary (0 or 1); detail goes to manifest + report

**Decision.** `runner.interpret_exit` produces:
- `wrapper_exit = 0` iff subprocess `returncode == 0`
- `wrapper_exit = 1` for everything else

The cause is captured in `manifest.exit_detail` and the report's
`Exit Code Detail` section: `raw_returncode`, `raw_returncode_hex` (for
high values), `platform`, `interpretation`, `interpretation_source`.

**Why.** Shell / CI need a binary success / failure. Anything else is
either misleading (mapping NTSTATUS to a number that collides with a
user-defined exit code) or lossy (truncating to one byte).

**Why not `returncode & 0xFF`** (the original plan's suggestion). On
Windows, `returncode = 0x100` (256). `0x100 & 0xFF == 0`. So a *failure*
would report as *success*. Caught by
`test_runner.test_overflow_256_does_not_become_zero` — explicit regression
guard.

**Why not cap to 255.** 255 is itself a common exit (ssh connection
failure, bash command-not-found). Mapping any failure to 255 confuses the
shell.

**Interpretation table.** Hand-curated list of common Windows NTSTATUS
codes (access violation, stack overflow, etc.) and POSIX signals (SIGKILL,
SIGTERM, etc.). Unknown codes go through with `interpretation_source = "unknown"` plus the raw hex. We do not maintain a complete NTSTATUS table —
the user can look up unknown values themselves.

---

## 15. Output scanner reads raw logs; evidence cites pattern + line, never raw text

**Decision.** `scanner.scan_output` runs over `stdout.log` and `stderr.log`
(*raw* logs, post-redaction would have hidden the patterns we want to
flag). The evidence string in each `RiskFlag` looks like
`stdout.log line 42 (2 occurrences)` — never the raw matched substring.

**Why scan raw.** Pattern `git reset --hard` would be untouched by the
redactor (no secret pattern matches), so reading raw is fine here. But
patterns that overlap with redaction (e.g. `Bearer …`) would be partially
hidden in the redacted log. Raw is more reliable.

**Why evidence excludes the raw text.** stdout might contain a secret. If
the secret happens to land near a high-risk pattern, including the raw
match would echo the secret into the report. Citing line + pattern label
is the smallest signal that lets a human investigate (open the raw log,
go to line 42) without leaking.

---

## 16. PowerShell equivalents in the output pattern list

**Decision.** Output patterns include both POSIX shell (`rm -rf`,
`chmod 777`) and PowerShell equivalents (`Remove-Item -Recurse -Force`,
`Invoke-Expression`, `iex`).

**Why.** Half of the agent runs in our target audience are on Windows.
Catching only POSIX would be performative — we'd miss the actual high-risk
patterns the agent is using.

**Why not full coverage of every shell ever.** Diminishing returns. POSIX
+ PowerShell covers >95% of agent invocations we expect.

---

## 17. Worktree / submodule: resolve `git_dir` via `git rev-parse --git-dir`

**Decision.** Whenever we need the real git directory, we shell out to
`git rev-parse --git-dir`. We never read `<repo>/.git` ourselves to check
if it's a directory or a file (gitlink).

**Why.** In a worktree, `<repo>/.git` is a *file* containing
`gitdir: /path/to/main/.git/worktrees/xyz`. In a submodule, it's a *file*
with `gitdir: ../.git/modules/sub`. Parsing this format ourselves is
error-prone; `git rev-parse` does it correctly and cheaply.

**Submodule policy.** v0.1 treats a submodule as an independent repo when
agentcam runs inside it. We do not analyze the submodule / superproject
relationship, do not recurse into nested submodules. If the user wants the
superproject view, they run agentcam from there.

**Sparse-checkout.** Not specially handled. The porcelain output reflects
the sparse view; we report what git reports.

---

## 18. Windows console encoding: degrade gracefully, mark in manifest

**Decision.** When `sys.stdout.buffer.write(chunk)` raises on Windows
console (cp950, cp1252, etc. don't accept arbitrary UTF-8 bytes), we
decode lossily and write text via `sys.stdout.write`, setting
`manifest.terminal_forward_degraded = true`. The raw log on disk is
unaffected (always bytes).

**Why.** The terminal display is convenience; the raw log is the source of
truth. Degrading display rather than crashing keeps the run usable.

**Why not "set console to UTF-8."** Side effects on the user's shell
session beyond agentcam's process. Not our place.

---

## 19. Redaction is best-effort — say so in README

**Decision.** README explicitly states: redaction is best-effort, may miss
new token formats, may miss multi-byte-encoded secrets, will not catch
free-form prose containing a secret value.

**Why.** The alternative (strong claims about completeness) creates
liability and breeds false trust. The honest framing is "we catch the
common shapes, the raw log is your forensic backstop."

---

## 20. Examples: one committed sample (`risky-auth-change`)

**Decision.** Only one sample report is committed:
`examples/risky-auth-change/expected-report.md`. Other scenarios
(safe-run, deletion, dependency change, pre-run dirty, command failure,
PEM streaming, secret-filename) are exercised exclusively by `tests/`.

**Why one, not three.** Repo cleanliness: less to drift, less to update
when report format changes. The risky-auth-change scenario is the most
load-bearing demo (matches the product framing) — safe-run sample is
boring, doesn't show product value.

**Why one, not zero.** First-time visitors need *something* to look at
without running the tool. Plus the README screenshot needs a source.

---

## 21. No `agentcam doctor`, no separate `risk-rules.md` / `report-format.md`

**Decision.** v0.1 has only `agentcam version` and `agentcam run`. The
docs are this single `design.md` plus the README; no separate rules or
format documents.

**Why.** `doctor` was specced as an environment-checker. The error
messages from `agentcam run` itself ("not in a git repository", "command
not found") cover the same use cases without a second subcommand.

**Why no separate docs.** Risk rule rationale and report format rationale
are integral to the design narrative — splitting them invites drift, where
the docs say one thing and the code does another. Section anchors in this
file (`## 7`, `## 12`, etc.) make it easy to deep-link.

---

## 22. Test expectations: keep them tight on safety, lenient on cosmetics

**Decision.** Tests assert:
- Exact non-leak conditions (no raw secret in redacted log, no raw token
  in evidence, no `.env.production` in markdown).
- Exact regressions for the blockers Codex caught (256 → 1, `auth` ≠
  `author`, PEM cross-chunk, staged-only diff visible, etc.).

Tests do *not* assert exact wording in human-readable sections. We can
rephrase a verdict line or a rollback paragraph without breaking the suite.

**Why.** Brittle tests on cosmetic strings make the test suite a tax on
phrasing improvements. Tight assertions on safety properties protect what
matters.

---

## 23. "No-diff" run cleanup: delete the run dir if pre and post state match

**Decision.** After collecting `state_after`, if (a) `head_before == head_after`,
(b) `porcelain_raw_before == porcelain_raw_after`, (c) the
`diff_fingerprint` matches (sha256 of `git diff` || NUL || `git diff
--cached` || NUL || untracked-file path/content bytes), AND (d) the wrapped
subprocess exited 0, AND (e) the user did NOT pass `--keep-empty`, then
`shutil.rmtree(run_paths.run_dir)` and return 0 with a stderr notice.
Otherwise generate the normal report.

**Why.** The product framing is "flight recorder" — recording should not
require user discipline per invocation. Combined with the Hook-mode path
on the roadmap (ROADMAP v0.2 #1), the model becomes "always record,
throw away if nothing happened." Without this cleanup, every chat-only
("alignment thinking") session leaves a zero-value report under
`.git/agentcam/runs/`, eventually degrading triage of the *interesting*
reports.

**Why include untracked file contents in the fingerprint.** A file that
existed as untracked pre-run and is rewritten in place by the agent has
the same path, same porcelain status (`?? path`), and is invisible to
`git diff`. Without hashing untracked bytes the fingerprint would match
across the rewrite → false-cleanup → agent's work disappears. Codex
adversarial review (2026-05-17) caught this hole before ship.

**Why fall through (not silent success) on `rmtree` failure.** On Windows,
AV scanners or held file handles can make `rmtree` fail mid-deletion.
The original `ignore_errors=True` would leave orphan log files on disk
while telling the user "report skipped" — confusing and lossy. The
chosen path catches `OSError` and branches on whether the run dir still
exists: (a) dir survives → fall through to normal report generation so
the user has *something*; (b) dir itself already removed (partial
failure or race) → log the failure and `return 0` without a report,
because `Path(report_md).write_text(...)` would `FileNotFoundError` on
a missing parent. Both branches print a clear stderr message. Codex
round-2 review caught the (b) sub-case before ship.

**Why a per-invocation flag (`--keep-empty`) instead of config.** Matches
the rest of agentcam: no config file, no implicit state, every behavior
is opt-in via argv. Anyone who wants the old "always keep" behavior
types one extra flag; everyone else gets the cleaner default.

**Why not just check `is_working_tree_dirty(state_after)`.** A pre-run
dirty tree + no-op agent is a common "alignment thinking" case — the
user wants to discuss with the agent without touching code. The dirty
state pre-existed and is not the agent's doing; recording it would be
duplicate of any prior agent-run report that already captured it.
Equality (before == after) handles this correctly; "is dirty"
over-keeps.

**Performance caveat.** Hashing untracked files is O(N) reads per
snapshot, where N is the count of untracked files NOT matched by
`.gitignore`. For repos with large unignored artifacts, this slows
down agentcam. The escape hatch is `--keep-empty` (skips the
fingerprint comparison's payoff but avoids the cost) plus the
encouragement to `.gitignore` build artifacts (which the user would
want regardless). Implementation detail: `compute_diff_fingerprint`
lives in `git_state.py` as a standalone function, called from `cli.py`
only when `not args.keep_empty`, so the flag genuinely skips the cost
rather than just disabling the cleanup branch.

**Known limitations.**
- *Untracked symlinks*: `_untracked_content_hash` reads files via
  `Path.read_bytes()`, which follows symlinks. An untracked symlink
  retargeted to a file with equivalent content produces an identical
  hash → false no-change. Rare; symlink-as-agent-output is uncommon.
- *Large untracked files*: `read_bytes()` loads each file fully into
  memory. Multi-GB unignored artifacts can spike RAM. Mitigation:
  keep large artifacts in `.gitignore`, or use `--keep-empty`.
- *Empty directories* and *`.gitignore`d artifacts* are invisible by
  design — the contract is "git-visible changes."
- *`git ls-files` failure*: returns a per-call unique sentinel from
  `_untracked_content_hash` (random nonce + return code), so a failed
  enumeration on either snapshot can NEVER match the other; cleanup
  is conservatively skipped and the report kept.

**Soft breaking change.** Pre-v0.2 behavior was "every run produces a
report." Post-cleanup, no-diff success runs produce nothing. CHANGELOG
entry must mention this and point to `--keep-empty` for users who
relied on the old default.

---

## 24. Hook mode: SessionStart / SessionEnd, not per-prompt

**Decision.** Hook mode (`agentcam hook-session-start`,
`agentcam hook-session-end`) integrates with Claude Code's
`SessionStart` and `SessionEnd` hook events, not `UserPromptSubmit` /
`Stop`. Both hooks read Claude Code's JSON payload from stdin
(`session_id`, `cwd`), exit 0 unconditionally, and persist state to
`<git_dir>/agentcam/sessions/<sanitized-sid>/state_before.pickle`
via atomic `.tmp` + `os.replace`. SessionEnd loads the snapshot,
validates schema + types, runs the same no-diff cleanup comparison
as the wrapping path, and either generates a report under
`runs/<run_id>/` or cleans up silently. Session dir is always
removed on SessionEnd.

**Why session-level, not per-turn.** UserPromptSubmit / Stop fire per
user prompt, giving N reports per session for N turns. SessionStart /
SessionEnd fire once per session lifetime. The session-level diff
captures the cumulative effect — what the agent did across the whole
conversation — which is closer to what the user wants when reviewing
"what happened during this work". Per-turn would produce one report
per "hi → ok" exchange even when the agent didn't change anything.

**Why exit 0 unconditionally.** Hooks that exit non-zero block Claude
Code. agentcam crashing must NEVER prevent the user from using
Claude. All exceptions are caught at the top of `cmd_hook_session_start`
and `cmd_hook_session_end`; the failure-path `print()` is itself
wrapped in try/except because stderr could be closed. Failures degrade
silently to "no report for this session" — bad, but not blocking.

**Why pickle for persistence (not JSON).** GitState contains `bytes`
(porcelain_raw) and nested dataclasses. JSON would need custom
serializers for each. Pickle is convenient and the trust model is OK:
files live under `.git/agentcam/sessions/` which is local-only and
write-controlled by the user. SessionEnd validates the loaded
snapshot's `schema_version` and the runtime types of every field used
downstream (`state` is `GitState`, `started_at` is `datetime`, etc.)
before trusting it — a malformed-but-loadable pickle is discarded
with cleanup, not used.

**Why atomic write (.tmp + os.replace).** SessionEnd could fire while
SessionStart is mid-write (e.g. Claude Code crash during startup
hook). Without atomicity, SessionEnd would read a partial pickle,
fail validation, discard, and lose what would have been a valid
snapshot if SessionStart had finished. The atomic rename guarantees
SessionEnd sees either the fully-written snapshot or nothing.

**Why duplicate SessionStart preserves the first snapshot.** Claude
Code fires SessionStart again on resume / clear / compact. Overwriting
would discard changes made between the original SessionStart and the
duplicate — a silent data loss. The implementation checks
`state_file.exists()` and returns 0 early. The eventual SessionEnd
compares against the very first snapshot, so the report covers the
full session lifetime including all resumed segments.

**Why session_id sanitization.** Raw session IDs from Claude Code are
opaque strings; in principle they could contain `..`, slashes, NUL,
or other path metacharacters. The sanitizer replaces anything outside
`[a-zA-Z0-9_-]` with `_` and caps length at 64. Path traversal is
structurally impossible after sanitization (always a single segment
under `sessions/`). Test
`test_session_id_with_path_traversal_is_sanitized` covers this.

**Why no stdout/stderr capture in hook mode.** Hooks cannot intercept
Claude Code's own stdout/stderr — they're piped to the terminal, not
to the hook subprocess. The hook only sees the JSON payload Claude
Code chose to expose (`session_id`, `cwd`, `transcript_path`). To
capture transcript text we would have to parse `transcript_path`
(JSONL file), which is a v0.3+ improvement. Hook mode reports show
empty placeholder log files; the Logs section in the report wording
will be misleading until a `capture_mode: hook` manifest field
exists.

**Known limitations.**
- *Sanitized session-id collision*: two distinct raw IDs that
  sanitize to the same string would share a session dir → reports
  could collide. Real Claude Code session IDs are UUIDs (collision
  probability negligible), so this is theoretical. A `sha256(raw)[:12]`
  suffix would close it; deferred until evidence of real-world
  collision.
- *Windows reserved names* (`CON`, `PRN`, `AUX`, `NUL`): same as
  above — UUID mitigation in practice, theoretical risk only.
- *Concurrent SessionStart TOCTOU*: two SessionStart processes racing
  could both pass `state_file.exists()` before either writes, then
  both write, with one winning (last write wins). Claude Code docs
  imply matching hooks are deduplicated; single-install case is
  unaffected. Robust fix (lock dir / `O_EXCL`) deferred.
- *Orphaned session dirs*: if Claude Code crashes between
  SessionStart and SessionEnd, the session dir is never cleaned up.
  A future `agentcam cleanup-orphans` command (or implicit cleanup
  at next SessionStart) would address.

**Why not "fold this into agentcam run".** Hook mode and wrap mode
have different correlation models (cross-invocation session id vs
single-invocation argv), different log capture (none vs stdout/stderr
tee), and different invocation contexts (stdin JSON vs argv). One
unified entry point would compromise the readability of both. Keeping
them as parallel paths (sharing `compute_diff_fingerprint`,
`collect_git_state`, `render_report`, the no-diff comparison) is
cleaner.

---

## Implementation notes (things that surprised us mid-build)

- **PEM regex original spec was wrong.** Plan wrote `[A-Z ]+`, which fails
  PKCS#8 (`-----BEGIN PRIVATE KEY-----` with no algo prefix). Fixed to
  `(?:[A-Z0-9]+ )?` (optional prefix, also covers `ED25519`).
- **`em-dash` in CLI output crashes Windows console** (cp950 can't encode
  it; you see `��`). All CLI-printed messages use ASCII punctuation.
- **`argparse.REMAINDER` keeps the leading `--`** in the captured argv.
  Strip it via `_strip_leading_dashdash`.
- **Tests use `sys.executable`** (the venv Python) to invoke
  `agentcam.cli`, not a hardcoded `python` from PATH. Cross-environment
  reliability.
- **Output scanner test had a false-failure mode** when the user's command
  itself echoes the matched string. Fixed by asserting only that the raw
  text doesn't appear in the *Risk Flags section*, since the *Command*
  section trivially echoes whatever the user typed.

---

## Implementation caveats discovered post-hoc

Items discovered during the Codex source-review fix batch (2026-05-16) and a
follow-up Claude self-spot-check. They are NOT in the original 22 decisions.
The next agent shouldn't try to "fix" these without understanding the
trade-off — and shouldn't assume the v0.1 source is fully externally validated
just because pytest is green.

### Caveat 1: `_escape_for_cmd_shim` over-escapes literal `^` in argv

`src/agentcam/runner.py` caret-doubles `^` regardless of whether it sits
inside `list2cmdline`-quoted segments. cmd.exe inside double quotes does NOT
treat `^` as an escape character, so a literal `^` in user argv (e.g. a
password containing `^`) becomes `^^` on the cmd line, and the `.cmd` /
`.bat` shim may receive two literal carets instead of one.

**Why we accept this**: a precise quote-aware caret pass would require a
parser for cmd.exe's grammar (which is gnarly). The over-escape is safe in
direction (never under-escapes a metachar) and rare in practice. Users who
need precise pass-through can wrap their own shell: `bash -lc "..."`.

### Caveat 2: `_relative_to_git_root` falls back to absolute in `git worktree`

`src/agentcam/report.py`'s `_relative_to_git_root(absolute_path, git_root)`
catches `ValueError` from `Path.relative_to()` and returns `absolute_path`
as-is. This fallback fires in `git worktree` setups, where the real
`git_dir` lives at `<main_repo>/.git/worktrees/<wt_name>/` while `git_root`
is the worktree's working tree directory — agentcam output lands under the
real `git_dir`, so the redacted log paths in the report fall back to
absolute strings, leaking username / repo location.

**Why we accept this**: full worktree path-rewriting requires resolving the
worktree's own root vs. the main repo's gitlink. Decision §17 already says
v0.1 in worktree = treat as independent repo, no cross-repo analysis. This
caveat is the specific case where that simplification leaks.

### Caveat 3 (RESOLVED 2026-05-16): Cross-platform validation

GitHub Actions matrix (auto-triggered on push to main, run #25961418769):

- ✅ ubuntu-latest × Python 3.11 — 172 passed (30s)
- ✅ ubuntu-latest × Python 3.12 — 172 passed (36s)
- ✅ macos-latest × Python 3.11 — 172 passed (32s)
- ✅ macos-latest × Python 3.12 — 172 passed (32s)
- ✅ windows-latest × Python 3.11 — 171 passed + 1 skipped (1m30s)
- ✅ windows-latest × Python 3.12 — 171 passed + 1 skipped (1m21s)

All three major platforms × both supported Python versions are green on
real CI runners (not just local emulation).

The Codex POSIX risks listed below remain valid as future-improvement
items (see ROADMAP "POSIX hardening"). They're issues the test suite
**doesn't cover** even when running on POSIX, not failures:

The Codex cross-platform risk assessment identified 3 POSIX-specific
concerns that the test suite does NOT exercise even when run on Linux
(see ROADMAP v0.2 "POSIX hardening" entry):

1. `run_wrapped` SIGINT cleanup only kills the direct child, not the
   process group — `bash -lc` etc. can leave grandchildren. Fix needs
   `start_new_session=True` + `os.killpg()` on POSIX.
2. `parse_porcelain_v1z` / `_git_text` decode with `errors="replace"`;
   POSIX filenames can be arbitrary bytes, so non-UTF8 names get
   corrupted before scanner / redaction sees them. Fix needs
   `surrogateescape` or byte-preserving handling.
3. `resolve_command` on POSIX skips the executable-bit / shebang
   verification that cmd.exe gives for free; "command found but not
   executable" failure mode is silent until subprocess actually runs.

These are documented and accepted for v0.1; addressed in v0.2.

### Caveat 4 (RESOLVED 2026-05-16): External confirm-review on source

Codex did two adversarial reviews on the plan and one on the source (which
found the 9 bugs that have now been fixed). A post-fix confirm review was
attempted three times via the `codex-rescue` subagent forwarder; all three
hung in a Codex CLI shared-session deadlock (subagent timed out with no
result). On the fourth attempt I bypassed the forwarder and called
`codex exec` directly via Bash — that worked synchronously, and Codex
returned `OK` for each of the 9 fixes plus `NO BLOCKERS`.

So the external confirm exists, but the lesson for future agents:
**when `codex-rescue` subagent fails repeatedly with session deadlocks,
fall back to `codex exec ... <<EOF` directly via Bash**. The direct CLI
path doesn't share the forwarder's session pool.

Note: Codex's reply was 9× `OK` with no per-fix detail beyond that. If
something subtle is wrong with a specific fix it might not have surfaced.
Caveats 1 and 2 (Claude self-spot-check partials) still apply as
known-shipped limitations.

---

## 25. Dependency manifest probe: pip + npm + pyproject, vs-HEAD baseline

**Decision.** `src/agentcam/dependency_probe.py` walks the changed-file
list, identifies recognized manifests by basename, parses each at HEAD
(`git show HEAD:<path>`) and at the working tree, then diffs the
parsed dep maps. The renderer emits an optional "## Dependency
Changes" section grouped by `(ecosystem, manifest_path)`. Parsers
shipped in v1: `requirements.txt`, `pyproject.toml` (PEP 621 +
Poetry), `package.json` (`dependencies` + `devDependencies`).

**Why vs HEAD, not vs pre-run snapshot.** Reading manifest content at
SessionStart (hook mode) or pre-subprocess (wrap mode) would be more
accurate but requires capturing & persisting `dict[path, bytes]` in
both code paths. vs-HEAD is one `git show` per changed manifest,
stateless, and works for both modes uniformly. The accuracy gap
appears only when `pre_run_dirty=True` — and we already surface that
flag in the report header. The Dependency Changes section adds a
one-line "vs HEAD" caveat when the working tree was dirty pre-run,
so the user knows to interpret accordingly.

**Why scrub URL credentials at the parser boundary.** Pip, npm, and
Poetry all accept `git+https://USER:TOKEN@host/...` as a dep target.
Without scrubbing, the credential would round-trip from the manifest
into `DependencyChange.new_version`, then into the Markdown report —
which gets shared, committed, pasted into PR comments. The scrub uses
a regex on URL specs that replaces `user:pass@` with
`<redacted-credential>@`, applied once at every parser entry. Defense
in depth: even if a future renderer reads `DependencyChange` and dumps
`new_version` directly, the credential cannot be there.

**Why namespace optional / dev / group deps.** PEP 621 lets the same
package appear in `[project.dependencies]` and
`[project.optional-dependencies.test]` with different specs. Poetry
has the same with `[tool.poetry.group.dev.dependencies]`. npm has
`devDependencies`. A flat `{name: spec}` dict would silently overwrite
on collision and miss the version change. Keys are namespaced with
`" [optional.test]"`, `" [poetry.dev]"`, `" [devDependencies]"` —
spaces and brackets cannot appear in PEP 508 / npm package names, so
collisions with real keys are structurally impossible.

**Why reject `..` and absolute paths in `scan_dependencies`.** The
function is public; an external caller could pass externally-derived
paths. Without the check, `_read_working_tree` would resolve
`../requirements.txt` and `_git_show_head` would return None —
producing a fake "all added" diff against an outside-repo file. The
reject is silent (just skip), no error surface.

**Why not Cargo.toml / go.mod / lockfiles yet.** Cargo and Go follow
the same pattern and would be ~20 lines plus tests each; held back so
the v1 surface stays reviewable in one sitting. Lockfiles
(`package-lock.json`, `poetry.lock`, `uv.lock`) deliberately not
parsed — most version bumps in lockfiles are transitive, low semantic
value, and would drown out direct-dep changes.

**Known limitations.**
- `pre_run_dirty=True`: diff is vs HEAD, so any manifest edits the
  user had staged or unstaged pre-run get attributed to the agent
  run. Surfaced via the section caveat above.
- Renamed manifests are treated as unrelated files: the old name is
  diffed (vs HEAD) and reports "all removed"; the new name reports
  "all added". No cross-rename matching in v1.
- Hook-mode probe failure leaving orphan run dirs: addressed in a
  separate cleanup pass (broader than this probe — see ROADMAP).

---

## 26. `ReportBundle` aggregator, not full event-stream layer

**Decision.** `ReportBundle` (in `agentcam.models`) consolidates
manifest + before/after `GitState` + risk_flags + dependency_changes
into a single dataclass. `render_report` accepts either a Bundle (the
preferred new shape) or the legacy 5-positional-arg call.
`cli.py` / `hooks.py` build a Bundle and call `render_report(bundle)`;
the legacy form is kept so the existing 25+ test cases don't need a
big-bang rewrite.

**Why a Bundle, not a full event stream.** An earlier design proposal
specified an event-stream layer (producers call `record(event)`,
events accumulate as a list, a reducer constructs the "report view"
that renderers consume). That layer was deliberately scoped down to a
Bundle. The motivating use cases for unlocking — SARIF output (#7),
PR-comment renderer (#3) — are both batch consumers: they need a
finished snapshot of risk_flags / dep_changes / state, not a stream.
The event-stream layer's distinct capabilities (persist, replay,
streaming consumers, multiple incremental consumers) have no current
consumer. Building an unused mechanism violates the project's
"don't refactor for cosmetics" rule. Bundle is the reducer's output
minus the stream; if a future streaming use case appears (live
dashboard, `agentcam tail`), the event layer can be added on top
without disrupting Bundle.

**Why dual signature on `render_report`.** The legacy positional form
`(manifest, state_before, state_after, risk_flags,
dependency_changes=None)` is dispatched-to by an `isinstance` check.
External users (and 25+ existing tests) keep working. New code uses
`render_report(bundle)`. A future cleanup commit can drop the legacy
form once dependents migrate. `assert` on legacy-required args was
replaced with explicit `raise TypeError` so the requirement survives
`python -O`.

**Why `frozen=True` but mutable list fields.** `ReportBundle` uses
`frozen=True` so field rebinding (`bundle.risk_flags = ...`) raises.
The `risk_flags` and `dependency_changes` fields are typed as `list`,
not `tuple`, because (a) the upstream `RiskFlag` / `DependencyChange`
producers already return lists, (b) Python convention here is list,
(c) `tuple` would force every caller through a `tuple(...)` cast.
Renderers must treat the lists as read-only by convention. Two
lock-in tests in `tests/test_report.py::TestReportBundle` pin both
halves of this boundary explicitly so a future list-vs-tuple
discussion has to update both.

---

## Out-of-scope reminders (do not add these without re-reading §10–§22)

- Sandbox / process isolation
- Pre-execution blocking / approval gating
- Auto-rollback / `git clean -fd` suggestions
- Cloud upload / telemetry of any kind
- VS Code / IDE integration
- GitHub App / GitHub Action (deferred to v0.2 if and only if v0.1 picks
  up traction)
- Custom YAML risk rules
- Multi-run dashboard
- Hosted SaaS dashboard

If a feature request hits any of these, the answer is "v0.2+, document the
ask in an issue." See README "Known limitations" for the user-facing
version of this list.
