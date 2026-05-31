---
description: Investigate the specified target. Code changes are forbidden.
---

@planner

Target: `$1`

Investigate the target without changing code.

## Investigation Rules

- The specified target is an initial hypothesis.
- Check `rg` / imports / call sites / tests / config / entrypoints.
- Check for related legacy / deprecated / similar implementations.
- Check for conflicts between documentation and implementation.

## Output

- Initially specified files
- Additional files checked
- Current state
- Related call path
- Problems
- Recommended next action
