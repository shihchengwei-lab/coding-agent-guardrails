# Corridor: example-feature

## Scope
One or two lines describing the minimal change. Replace this whole file when
you start a real task (or generate it with /slime-corridor).

## Semantic Delta
- This task changes: the smallest observable behaviour that must move.
- This task preserves: existing APIs, data flow, architecture, naming, and
  ownership boundaries unless a Goal Frontier item explicitly requires moving
  them.

## Non-goals
- Do not add parallel architecture, new dependency, broad refactor, or public
  API change unless this corridor names the evidence for it.

## Paths
- lib/feature/example/**
- test/feature/example/**

## Goal Frontier
- The behaviour the acceptance criteria require, traced back from the criteria.

## Start Frontier
- lib/feature/example/example_service.dart:ExampleService — the seam the
  change attaches to.

## Stop Condition
- `dart test test/feature/example/` is green.
