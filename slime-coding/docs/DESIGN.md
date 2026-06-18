# Design & reference

Mechanics behind Slime Coding. For the *why* and the manual method see
[`CONCEPT.md`](CONCEPT.md); for what's actually been validated see the
[README status section](../README.md#status--experimental-honestly) and
[`../reports/`](../reports/).

## Core principle: request vs enforcement

- **A prompt is a request.** "Don't do X" in `CLAUDE.md` can be skipped by the
  model.
- **A hook is enforcement.** It runs every time its condition matches,
  regardless of what the model remembers.
- **Teeth only on unambiguous signals.** Hard-blocking on a fuzzy judgement
  trains users to disable the hook — worse than no gate. So the gates take only
  git facts; fuzzy signals are report-only.

## The four layers

| layer | carries | mechanism | teeth |
|---|---|---|---|
| L0 discipline | frontier rules, corridor artifact | `CLAUDE.md` + `slime-navigate` skill + `corridor.md` | none (request) |
| L1 state | cross-round pruned records | `PRUNED.md` + injection hook | injection is certain; content is state |
| L2 gates | hard block on git facts | command-type hook (block) | yes |
| L3 measurement | fuzzy cost signals | report-only hook | none (report only) |

### L0 discipline
The `slime-navigate` skill templates five outputs: Goal Frontier, Start
Frontier, Meeting Corridor, Pruned Paths, Stop Condition. Paste
`templates/CLAUDE.slime.md` into the project's `CLAUDE.md`. The corridor is
written to `.slime/corridor.md`, read by L2 and L3.
> The built-in Explore / Plan sub-agents skip `CLAUDE.md`, so keep the
> exploration discipline on the main agent.

### L1 state (pruned records)
The failure it fixes: the agentic loop revives a design rejected last round
because the rejection reason left the context.
- File `.slime/PRUNED.md`: committed, survives across sessions, append-only.
- `bin/prune-inject` runs on SessionStart + UserPromptSubmit and injects via
  `additionalContext`.
- **Decay**: inject only records tied to the current corridor or the most recent
  N (`SLIME_PRUNE_RECENT`, default 5), so `PRUNED.md`'s monotonic growth doesn't
  linearly burn tokens.
- Reaching the editing sub-agent: sub-agents have their own context and don't
  receive the main session's injection. Cover it two ways — `CLAUDE.md` says
  "read `.slime/PRUNED.md` before editing", or the planner copies the pruned
  summary into the task prompt.

### L2 gates (all command-type, zero inference)
`bin/patch-cost` takes only git facts; three hard blocks:
- **New dependency**: the Stop hook diffs `pubspec.yaml`'s `dependencies` keys →
  a new one blocks, demanding a keep/remove decision.
- **Prune logging**: Stop hook — `SLIME_TEST_CMD` exits non-zero **and**
  `PRUNED.md` has no uncommitted change vs HEAD (i.e. nothing logged this round)
  → block, demanding the abandoned path be written to `PRUNED.md`. Detection is
  `git status --porcelain` (working-tree dirty), not a Claude Code session
  boundary.
- **Corridor gate**: PreToolUse on `Edit|Write` — `deny` when
  `.slime/corridor.md` is missing or still the template (id `example-feature`,
  empty `## Paths`, or the example globs). Writes under `.slime/` are always
  allowed, so a corridor can be bootstrapped without a deadlock.
  > Cost: this is not a hard security boundary — an agent can widen
  > `corridor.md` first, then edit elsewhere. Widening the corridor may be
  > legitimate new evidence, so it isn't blocked; L3 surfaces it instead.

### L3 measurement (never blocks)
`bin/patch-cost` at Stop emits a `systemMessage` cost report: touched / new
files, public-API additions (Dart `export` / `class` / …), out-of-corridor files
(from `corridor.md`'s `## Paths`), and whether `corridor.md` changed this round.
`systemMessage` is shown to the **user** (L3 is a human-facing cost signal); it
never blocks, so a false read can't escalate to abandonment.

## Install details

`install.sh` (idempotent, backs up `settings.json`):

1. Wires the two hook scripts (`prune-inject`, `patch-cost`) into the project's
   `.claude/settings.json` across four events (SessionStart, UserPromptSubmit,
   PreToolUse, Stop). Commands use this clone's **absolute path**, quoted and run
   via `python3` (spaces are safe; no dependency on the executable bit). Only
   existing Slime Coding hooks are replaced; your other hooks are untouched.
2. Symlinks the `slime-navigate` skill and the `/slime-corridor` /
   `/slime-prune` commands into `.claude/` (so `git pull` on the clone updates
   them).
3. Seeds `templates/.slime/` if the project has none (replace the template
   before editing code — the template corridor is blocked by L2).

Manual step (L0 is a request, not enforced): paste `templates/CLAUDE.slime.md`
into the project's `CLAUDE.md`.

> Manual install: replace `__SLIME_HOME__` in `hooks/hooks.template.json` with
> the clone's absolute path and merge it into `.claude/settings.json`.

## Config (env)

| var | default | effect |
|---|---|---|
| `SLIME_PRUNE_RECENT` | `5` | L1: most-recent N pruned records to inject; `0` = corridor-match only; non-numeric / negative falls back to 5 (never crashes) |
| `SLIME_TEST_CMD` | unset | check command for the L2 prune gate; unset → that gate degrades |
| `SLIME_TEST_TIMEOUT` | `600` | check timeout (seconds) |
| `SLIME_PUBSPEC` | `pubspec.yaml` | dependency-manifest path (change for non-Dart) |

## Slash commands

- `/slime-corridor [id]` — create / update `.slime/corridor.md`.
- `/slime-prune [reason]` — append a rejected design to `.slime/PRUNED.md`.

## Artifact formats

`.slime/corridor.md` needs a `# Corridor: <id>` line and a `## Paths` list
(globs). Each `.slime/PRUNED.md` record starts with `## [date] corridor:<id>`.
Examples in `templates/.slime/`.

## Layout

```text
slime-coding/
├── install.sh                          # run this against a target project
├── hooks/hooks.template.json           # hook-wiring template (__SLIME_HOME__ placeholder)
├── bin/
│   ├── patch-cost                      # L2 certain subset + L3 fuzzy subset
│   └── prune-inject                    # L1 injection + decay
├── skills/slime-navigate/SKILL.md      # L0
├── commands/{slime-prune,slime-corridor}.md
├── templates/
│   ├── CLAUDE.slime.md                 # L0 — paste into project CLAUDE.md
│   └── .slime/{corridor.md,PRUNED.md}  # artifact examples
├── tests/test.sh                       # hook behaviour tests
├── docs/, experiments/, reports/       # concept, validation harness, results
└── README.md
```

## Tests

`tests/test.sh` (needs python3 + git) runs the hook behaviour tests: corridor
gate, bootstrap exemption, template rejection, `SLIME_PRUNE_RECENT` edge values,
the Stop dependency / prune gates.

```bash
./tests/test.sh
```

## Assumptions & limits

- Requirements must be writable as observable acceptance criteria; vague tasks
  need discovery first.
- The prune gate needs a runnable check (`SLIME_TEST_CMD`); without one it
  degrades.
- The decay keys (corridor id / recent N) bound the context cost; recent N is
  `SLIME_PRUNE_RECENT`.
- The L2 dependency gate currently targets Dart/Flutter `pubspec.yaml`; change
  `SLIME_PUBSPEC` and the `bin/patch-cost` parser for other ecosystems.

## References

- Hooks: https://code.claude.com/docs/en/hooks
- Sub-agents: https://code.claude.com/docs/en/sub-agents
- Settings (hooks live in `.claude/settings.json`): https://code.claude.com/docs/en/settings
