# Mechanism verification — 2026-06-18

Scope: the **mechanism layer only** (validation plan Q1/Q2/Q3, the "機制驗證
成功" threshold in §11). This report makes **no** claim about whether Slime
Coding reduces over-implementation — that is the effect layer (Q4/Q5), which
requires the multi-condition benchmark and has **not** been run.

## What was verified

Phase A of the plan (§13) — the seven edge cases — plus the existing gate
tests, all run by `tests/test.sh` (19 checks, stdlib + git only):

| Plan §11 criterion | Check | Result |
|---|---|---|
| CI passes | GitHub Actions `ci.yml` | green |
| `tests/test.sh` passes | 19/19 | pass |
| `install.sh` idempotent (twice) | CI smoke test | pass |
| missing corridor blocked | test 1 | pass |
| template corridor blocked | tests 3, 10, 11 | pass |
| `.slime/` bootstrap not blocked | test 2 | pass |
| dependency gate reproducible | tests 8, 14 | pass |
| prune gate reproducible | tests 7, 15 | pass |

Phase A specifics (plan §13):

1. corridor without `## Paths` → deny (test 10)
2. template example glob → deny (test 11)
3. valid corridor + out-of-corridor edit → PreToolUse allows, Stop report lists
   it (tests 12, 13)
4. missing `pubspec.yaml` → dependency gate degrades, no block (test 14)
5. `SLIME_TEST_CMD` timeout → degrades, no crash/block (test 15)
6. multi-record `PRUNED.md` → inject matching-corridor + recent N only (test 16)
7. `SLIME_PRUNE_RECENT=0` → inject matching-corridor only (test 17)

None of the seven exposed a defect; the implementation already handled them.

## Refinement found during verification

Building the metrics collector surfaced that `.slime/corridor.md` and
`.slime/PRUNED.md` edits were being counted as "out-of-corridor" in the L3
report, double-counting with `corridor changed` and penalising the *required*
prune-logging. Fixed in `bin/patch-cost` and `experiments/metrics.py`; guarded
by test 18.

## Harness delivered (not yet exercised for effect)

- `experiments/` scaffold: `new-run.sh` (materialise a fixture as an isolated
  git repo), `metrics.py` (git-derived columns; human columns left null),
  `schema/metrics.schema.json`, task cards `tasks/T1..T8.md`, fixture
  `fixtures/cli-notes` (passing baseline tests).

## Honest status (plan §15 anti-hype)

- Verified: the gates fire on the unambiguous git facts they claim to, the
  bootstrap path is not deadlocked, and the install is idempotent.
- **Not** verified: any reduction in patch cost, any effect on task success
  rate, or that the discipline survives real agent runs. No benchmark numbers
  exist yet, so none are reported. README positioning stays "experimental
  workflow", per §16.

## Next step

Smoke benchmark (plan Phase C): conditions A vs C on T1, T2, T3, T5, T6, T7 on
`cli-notes`, 1 run each, producing the first `reports/<date>-smoke-report.md`.
This needs real agent runs under each condition and human review; it is not
something to synthesise.
