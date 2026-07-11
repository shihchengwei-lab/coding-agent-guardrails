# Corridor: example-feature

## Rigor
normal

## Outcome
The smallest observable result that must become true, plus the important
behavior or boundary that must remain unchanged.

## Paths
- lib/feature/example/**
- test/feature/example/**

## Evidence
- Supports: the acceptance test reaches ExampleService through the existing
  caller.
- Would falsify: runtime tracing shows another component owns this behavior.
- Dependency: <package> — <why this outcome cannot use the existing stack>.

## Stop Condition
- Command: dart test test/feature/example/
