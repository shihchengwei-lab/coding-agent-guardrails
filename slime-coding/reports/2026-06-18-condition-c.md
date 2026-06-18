# Condition C (hooked) — dependency gate — 2026-06-18

Question (plan Q2 / "do the gates add anything beyond the prompt-only
discipline?"). Focus: the **L2 Stop dependency gate**, the gate with the
hardest teeth.

## Faithfulness note (read first)

A fully automated condition C would require Claude Code's hook machinery to
intercept the agent-under-test's own tool calls. A spawned sub-agent's calls
are not something this session can make the hooks fire on, so this is **not** an
automated C run like the A/B benchmarks. Instead:

- The dependency gate's mechanism is exercised with the **real `bin/patch-cost`
  script** on a real `pubspec.yaml` diff.
- The Stop-hook *loop* (block → the model receives the reason → it addresses it
  → stop) is reproduced by delivering the **actual block text** the script
  emitted to an agent and letting it fix the repo. (`SendMessage` to continue
  the same agent isn't available here, so a fresh agent receives the block on
  the same repo state — mechanically the same effect.)
- The PreToolUse corridor gate was satisfied with a pre-written corridor; its
  blocking is verified separately and deterministically by `tests/test.sh`.
- Fixture: new `experiments/fixtures/dart-mini-app` (the gate parses
  `pubspec.yaml`). No Dart toolchain, so code is reasoned about, not run; the
  dependency gate needs only the manifest diff.

N is tiny (3 natural + 1 backstop). This is a mechanism demonstration plus a
small behavioural probe, not a benchmark.

## What happened

**Gate mechanism (real script).** On the fixture: a clean Stop emits the L3
report and no block; after a `timeago` dependency is added to `pubspec.yaml`,
Stop returns `decision: block` naming `timeago` and flags `pubspec.yaml` as
out-of-corridor. (Both observed directly.)

**Natural runs (3×), discipline prompt, gate available as backstop.** The task
("add `relativeTime(DateTime)`") mildly tempts a date package, and the prompt
did **not** forbid dependencies — the gate was meant to be the enforcement. All
three disciplined agents hand-rolled the function with stdlib `Duration` math
and **did not touch `pubspec.yaml`**. Run 2 explicitly recorded the rejected
`timeago` package in `.slime/PRUNED.md`. So the dependency gate **never had to
fire** — the discipline alone already avoided the dependency.

**Backstop loop (1×), end-to-end.** To exercise the gate's actual job, an agent
that *reached for a package* was simulated (`timeago` added to `pubspec.yaml`
and used in `lib/notes.dart`). Then:
1. Real `patch-cost` Stop → `block`, naming `timeago`, pubspec out-of-corridor.
2. That exact block text handed to an agent → it removed `timeago`,
   reimplemented `relativeTime` with stdlib, and (correctly) deleted the stray
   `import`.
3. Real `patch-cost` Stop re-run → **no block**; clean cost report.

Artifacts: `experiments/runs/2026-06-18-condition-c/` (natural diffs;
backstop `stop-block.json` + `final.diff.patch`).

## Honest reading — does the gate add anything beyond the prompt?

- **On a compliant agent: no marginal reduction.** When the discipline prompt
  is obeyed, the agent doesn't add the dependency, so the gate is silent. It is
  not an extra reducer stacked on top of an already-disciplined agent.
- **Its value is as a backstop, and that backstop works.** When an agent *does*
  over-reach (the failure mode the prompt cannot guarantee away — a less careful
  model, a forgotten instruction), the gate blocks on the unambiguous git fact,
  names the offending package, and the block drives a correcting edit; the loop
  then passes. That is exactly the L2 role: hard enforcement of an unambiguous
  fact, versus L0's request.
- This matches the layered design: L0 changes the common case (shown in the
  extensibility report), L2 catches the non-compliant case (shown here). They
  are not redundant; they cover different cases.

## Limits / next

- Single gate (dependency), single fixture, no toolchain; the prune gate and
  the live PreToolUse interception were not exercised here (the latter is
  test-verified). 
- A real condition-C benchmark needs the hooks firing inside the
  agent-under-test's session — out of reach for spawned sub-agents here.
- The dependency gate is `pubspec`-specific; other ecosystems
  (`requirements.txt`, `package.json`) are not yet supported by `patch-cost`.
