# Coding Agent Guardrails

[繁體中文](README.zh-TW.md)

**CI green does not mean the change is complete. Complete means the person
taking over can understand the diff and take responsibility for merging and
maintaining it.**

Coding agents can finish the task, pass the tests, and turn CI green. The hard
part comes next: someone has to take over the diff, understand what changed,
take responsibility for merging it, and maintain it afterward. The model can
produce code, but the person who adopts, merges, and maintains that output is
responsible for it. This toolkit sits on the agent's side before that handoff.
It keeps the handoff facts visible: what changed, which checks ran, and where
the next person starts.

One install connects four tools that cover the path from "agent starts typing"
to "human presses merge". Each tool covers one stage:

| Stage | Tool | What it adds |
|---|---|---|
| Before the agent starts | [kiss-my-diff](kiss-my-diff/) × [slime-coding](slime-coding/) rules | One unified discipline block in your `CLAUDE.md` / `AGENTS.md` ([templates/DISCIPLINE.md](templates/DISCIPLINE.md)): smallest sufficient readable change, minimal semantic drift, stop when done. |
| While the agent works | [slime-coding](slime-coding/) hooks | Turn-scoped gates: direct edits are checked before writing; shell writes are checked immediately afterward and again at Stop. An OS sandbox, not a hook, is the filesystem security boundary. |
| After the agent claims done | [agentcam](agentcam/) | Records what actually changed: files, risk flags, diff stat, then drafts the PR handoff from that record. |
| Before a human reviews | [corridor-ci](corridor-ci/) | Validates the five-line handoff against the actual diff and appends the recorded evidence to the PR report. |

The collaboration discipline is one ordered loop, not four interchangeable
slogans: reduce the request to observable necessities (first principles), let
repo evidence support or falsify candidate routes (slime), choose the smallest
sufficient change rather than merely the shortest diff (Occam), then label
manual claims separately from recorded behavior. Read broadly, edit narrowly;
stop when the observable condition is met.

## Why a Vibe-Built Tool Needs Guardrails

This project is mostly implemented by coding agents. I am not a software
engineer, I do not write code, and I cannot judge a diff line by line. In
practice, I usually do not inspect much: if the benchmark looks good, the tool
runs, or the game moves, I tend to let it move forward.

That is the starting point. I use these tools loosely, and I may not even use
this whole toolkit consistently myself. The contradiction is the point: I vibed
together a tool for limiting vibe coding. The problem is also real. When coding
agents produce a lot of code quickly, the risk often lands in the handoff: what
changed, whether checks really ran, and whether the next person can take over.
Every tool here does one job: turn "trust me" into a recorded fact.

## Install (one command)

```bash
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails ~/guardrails
~/guardrails/install.sh /path/to/your/project
```

```powershell
git clone https://github.com/shihchengwei-lab/coding-agent-guardrails $HOME\guardrails
& $HOME\guardrails\install.ps1 -Project C:\path\to\your\project
```

Both entrypoints call the same Python 3.11+ installer core. It creates a
versioned runtime and virtual environment under `<git-dir>/guardrails/`, then
atomically wires absolute hook commands for both Claude Code and Codex. The
toolkit checkout can be moved or deleted after installation. Re-running is
idempotent: user hooks are retained, `.slime/corridor.md` and `PRUNED.md` are
create-if-absent, and a workflow is upgraded only when its managed marker and
official hash both match. Custom content is preserved with a warning.

The install also creates repo-local `guardrails` and `guardrails.cmd`
launchers. Configure executable trusted checks as argv, inspect the installed
runtime, or preview a safe uninstall with:

```bash
./guardrails check set primary -- python -m pytest -q
./guardrails doctor
./guardrails doctor --remote  # also inspect GitHub required contexts via gh
./guardrails uninstall --dry-run
./guardrails uninstall
```

Uninstall removes only content proven by `<git-dir>/guardrails/install.json`.
It preserves `.slime/`, trusted check configuration, and recording history by
default; `--purge-state` explicitly removes that retained state. Codex project
hooks still need to be reviewed once with `/hooks`.

## The loop

The four tools connect into one workflow. That is why they are packaged
together:

1. **Record**: `agentcam run -- <agent command>` (or use the installed
   Claude Code session / Codex turn hooks). Agentcam records the before/after
   Git state, changed-file list, and diff stat under `.git/agentcam/runs/`;
   wrap mode also keeps terminal output. Trade-off, disclosed: hook-mode
   evidence is thinner, because lifecycle hooks do not expose terminal output, so
   output-pattern risk flags (`rm -rf` and friends) are unavailable;
   wrap the session with `agentcam run` when you want the full record.
2. **Verify**: `agentcam verify -- pytest -q`. agentcam runs the check
   itself and records command, exit code, and duration: observed facts,
   not the agent's claim. Passing checks draft the handoff's `Verified`
   line.
3. **Hand off**: `agentcam handoff` prints the five-line corridor handoff
   drafted from the record. Paste it into the PR body, then fill in
   `Decision`, the line only the author can know (`Verified` too, if no
   recorded check passed).
4. **Attach evidence**: `agentcam export latest --files .agentcam/`
   writes the redacted run record in committable form; commit it with
   the PR.
5. **Gate**: corridor-ci on the PR validates the handoff against the
   actual diff and appends the recorded evidence (risk flags, recorded
   checks, diff stat) to its report. It labels author-controlled matching
   evidence as `local-recorded`, otherwise `manual` or `unverified`, and marks
   partial observation. Manual and partial
   provenance stay visible; a placeholder or false recorded claim fails the
   corridor.

Every tool also works standalone; each subdirectory has its own README.
Breaking upgrades are listed in [the migration guide](docs/MIGRATION.md).

A workflow file is not a merge gate by itself. Repository administrators must
make Corridor and the relevant test jobs required checks in branch protection
or a ruleset. This repository requires seven stable aggregate checks on `main`:
Policy Gate, Corridor, and the five product test aggregates.

This repository also runs `Policy Gate` from the default branch with
`pull_request_target`; it treats the PR head as data and never executes PR
scripts. A PR that changes `.github/workflows/**` needs an OWNER approval bound
to the exact current head SHA:

```text
Guardrails-Workflow-Approval: <full-head-sha>
```

After adding the comment, rerun the failed Policy Gate job. A later commit
invalidates the approval. This is an explicit maintainer break-glass for
workflow maintenance, not an approval that PR content can grant itself.

## Versioning

One repo, four tools, so release tags are prefixed per tool:
`agentcam-v0.5.0`, `corridor-ci-v13.0.0`, and the floating major tag
`corridor-ci-v13`. Earlier releases
(`v0.2.0`, `v10`, …) live in each tool's original repository.

## History

Each tool started as its own repository and was imported here with full
commit history. `git log` inside any subdirectory goes back to that
tool's first commit.

## License

MIT, for the toolkit and for every tool in it.
