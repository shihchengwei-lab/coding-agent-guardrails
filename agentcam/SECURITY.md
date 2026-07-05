# Security policy

## What agentcam is — and is not

agentcam is a **flight recorder** for AI coding agents. It records what
happened in your repo during a wrapped command and produces a Markdown
report. It is **not**:

- a sandbox
- a pre-execution gate
- a security scanner
- a DLP / compliance product
- an audit pipeline for SOC2 / ISO 27001 / PCI / HIPAA / GDPR / CCPA

If you need any of those, agentcam does not replace them.

## Threat model agentcam addresses

agentcam helps you answer, **after** an agent run finishes:

- What files did the agent change?
- Where (in this repo) might the change be sensitive — auth paths, secrets,
  CI workflows, deployment configs, dependency manifests?
- Did the agent print anything dangerous to stdout / stderr that a human
  should look at?
- How do I roll back this specific run cleanly?

## Threat model agentcam does NOT address

- **Live attacks during the run.** agentcam does not block the wrapped
  command. If the agent runs `rm -rf $HOME` and exits 0, agentcam will
  flag it in the report; the files will already be gone.
- **Sandbox escape.** The wrapped command runs in your normal shell with
  your normal credentials. There is no isolation.
- **Network exfiltration.** agentcam does not monitor or intercept network
  traffic.
- **Adversarial agents.** agentcam is built for "agent does roughly what
  it claims, but a careful reviewer wants a record." It is not built to
  defend against an agent deliberately trying to defeat the recorder.
- **Malicious hook payloads.** The hook subcommands
  (`agentcam hook-session-start` / `hook-session-end`) trust the JSON
  payload on stdin (`session_id`, `cwd`) supplied by Claude Code. A
  compromised or adversarial Claude Code could point `cwd` at an
  unintended repo, causing agentcam to snapshot that repo's state.
  Falls under "Adversarial agents" above — not separately defended
  against.

## Best-effort properties (not guarantees)

These are agentcam's design intent. None are warranted:

1. **Secret redaction.** agentcam redacts common token shapes
   (AWS / GitHub / OpenAI / Anthropic / Slack / npm / GitLab / Bearer /
   JWT / env-style assignments) and PEM private key blocks in the
   `*.redacted.log` files and in every Markdown surface of the report.
   The dependency-manifest probe additionally scrubs URL basic-auth
   credentials at the parser boundary: a `git+https://USER:TOKEN@host/...`
   entry in `requirements.txt`, `pyproject.toml`, or `package.json`
   becomes `git+https://<redacted-credential>@host/...` before the spec
   reaches `DependencyChange`, the report, or `manifest.json`. New
   secret formats may slip through. The raw log on disk preserves the
   original bytes for forensic review.

2. **Self-pollution avoidance.** Output is written under
   `<git_dir>/agentcam/runs/`, which git itself does not track. Agent
   invocations of `git add .` cannot stage agentcam's output. Verified by
   `tests/test_e2e.py::TestSmoke::test_git_status_does_not_list_agentcam`.

3. **Argv redaction.** Command argv passes through redaction before being
   shown in the Markdown `Command:` field. `manifest.command_argv_raw`
   preserves the original for forensics.

4. **Exit code transparency.** Wrapper exit is binary (0 / 1). The original
   subprocess returncode, platform, and a human interpretation
   (signal name on POSIX, NTSTATUS name on Windows when known) all go to
   `manifest.json` and the `Exit Code Detail` report section.

## Local data exposure surfaces

The following are kept on disk under `.git/agentcam/runs/<run_id>/`:

| File | Contents |
|---|---|
| `stdout.log` / `stderr.log` | **Raw** subprocess output, including any unredacted secrets |
| `stdout.redacted.log` / `stderr.redacted.log` | Redacted versions |
| `manifest.json` | Includes `command_argv_raw` (original argv) |
| `AGENT_RUN_REPORT.md` | Only references redacted logs and redacted argv |
| `sessions/<sid>/state_before.pickle` (Hook mode only) | Pickled snapshot of git state captured at SessionStart, including porcelain bytes and untracked-file content hashes. Cleaned up on SessionEnd. |

The `state_before.pickle` file uses Python's `pickle` format. An attacker
with write access to `.git/agentcam/sessions/` could replace it with a
malicious payload that runs arbitrary code under the current user when
`agentcam hook-session-end` loads it. This matches the trust model of
every other artifact under `.git/`: an attacker who can write to
`.git/agentcam/` can also write to `.git/hooks/`, `.git/config`, or
the working tree — write access to `.git/` is already root-equivalent
for the user. agentcam does not introduce additional risk beyond what
local write access already grants.

`.git/` is not tracked by git, so these files cannot be `git push`-ed by
accident. They **can** be exposed by:

- cloud sync of the working directory (OneDrive, Dropbox, iCloud Drive)
- system backup tools (Time Machine, Windows File History, Backblaze)
- zipping or copying the entire repo to share with someone
- a malicious process on the same machine reading user-readable files

If any of these matter for your environment, periodically clean
`.git/agentcam/runs/` and treat raw logs as confidential.

## Reporting a vulnerability

Please **do not** file public issues for security vulnerabilities.

Email: **shihchengwei@gmail.com** with subject `[agentcam security]`.

Include:

- A description of the issue and the impact
- A reproduction (commands, input, expected vs. observed behavior)
- Your platform (OS + Python version)
- Whether you'd like to be credited in the fix announcement

I'll acknowledge within 7 calendar days. There is no formal SLA: agentcam
is a personal-time project. If the issue affects user safety (e.g. raw
secret leakage to the redacted log, self-pollution regression), I'll
prioritize a fix and a release.

## Out-of-scope for security reports

These are **expected** behaviors, not vulnerabilities:

- Risk flags fire on heuristics that may produce false positives / negatives
  (the README and `docs/design.md` § 7 say so explicitly).
- The wrapped subprocess can do anything your shell can do (the README
  "Known limitations" says so explicitly).
- Raw logs contain whatever the subprocess wrote, including sensitive data.
  This is the design — see `docs/design.md` § 2.
- The `Command:` field shows the redacted argv. The raw argv lives in
  `manifest.command_argv_raw` by design.
- agentcam does not defend against an adversarial wrapped subprocess that
  tries to evade detection (e.g. by writing to files outside the repo).

If you're unsure whether something is in scope, email anyway and I'll
say.
