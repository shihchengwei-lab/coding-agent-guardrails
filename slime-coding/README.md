# Slime Coding

[![CI](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml/badge.svg)](https://github.com/shihchengwei-lab/slime-coding/actions/workflows/ci.yml)

![Slime Coding — grow both frontiers, commit only the minimal corridor](assets/slime-coding.png)

**Stop agentic AI from over-building.** Instead of generating code straight from
a prompt, Slime Coding makes the agent grow two frontiers — what the requirement
needs, and what the repo already offers — and only edit the **minimal corridor
where they meet**. Rejected designs are pruned and recorded so they don't come
back. It's wired into Claude Code as hooks, so the discipline is enforced, not
just requested.

## Why hooks

A line in `CLAUDE.md` ("don't over-engineer") is a **request** — the model can
skip it. A **hook** runs every time. Slime Coding puts the teeth only on
unambiguous git facts:

- **No edit without a corridor.** Define the minimal change in
  `.slime/corridor.md` first, or `Edit`/`Write` is denied.
- **New dependency is blocked at Stop** until you keep-or-remove it.
- **Pruned paths persist** in `.slime/PRUNED.md` and are re-injected next
  session, so the loop can't revive a rejected design.
- **Scope creep is reported** (touched / new files, out-of-corridor edits) —
  shown, never falsely blocked.

## Quick start

Clone anywhere, then run `install.sh` against your project (idempotent; backs up
`settings.json`):

```bash
git clone <this-repo> ~/slime-coding
cd /path/to/your/project
~/slime-coding/install.sh .
```

It wires the hooks into `.claude/settings.json` and links the `slime-navigate`
skill + `/slime-corridor` and `/slime-prune` commands. One manual step: paste
`templates/CLAUDE.slime.md` into your `CLAUDE.md`. Needs `python3` + `git`.

→ Full mechanics, config, and layout: **[`docs/DESIGN.md`](docs/DESIGN.md)**.
→ The idea and the manual method: **[`docs/CONCEPT.md`](docs/CONCEPT.md)**.

## Status — experimental, honestly

Not a validated framework; no "proven / production-ready" claims. What's known
so far (data in [`reports/`](reports/), plan in
[`docs/VALIDATION_PLAN.md`](docs/VALIDATION_PLAN.md)):

- **Mechanism: verified.** The gates fire on the git facts they claim, bootstrap
  doesn't deadlock, install is idempotent — `tests/test.sh` (19 checks) + CI.
- **Effect: a narrow, reproducible signal.** In small Python/Node A·B runs, when
  a prompt invites speculative extensibility ("we'll add more formats later"),
  the baseline builds a registry for the one required variant (13/13) while the
  Slime discipline suppresses it (1/13) — roughly half the code at equal
  behavior. **With no such invitation, there's no difference.** Other
  over-implementation baits (refactoring, gold-plating) didn't reproduce.
- **The dependency gate is a backstop**, not an extra win on a compliant agent.

## License

MIT — see [`LICENSE`](LICENSE). Changes in [`CHANGELOG.md`](CHANGELOG.md).
