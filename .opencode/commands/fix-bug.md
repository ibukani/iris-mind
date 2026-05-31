---
description: Investigate the specified bug and apply the minimal fix.
---

@debugger

Bug: `$1`

## Process

1. Confirm the symptom.
2. Investigate related files with falsification in mind.
3. Identify the cause.
4. Add a failing test when possible.
5. Apply the minimal fix.
6. Validate.

## Prohibited

- Unrelated large fixes
- Weakening tests
- Hiding the problem with mocks
