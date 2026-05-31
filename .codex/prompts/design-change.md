# Codex Prompt: Design Change

Read `AGENTS.md` first.

## Discovery requirement

Treat the user request and any listed files as initial investigation targets, not a complete scope.

Before editing:

1. Search for references to target classes/functions/config keys.
2. Inspect import sites and call sites.
3. Inspect related tests.
4. Inspect configuration, registration, and runtime entrypoints.
5. Look for parallel, legacy, deprecated, or similarly named implementations.
6. Identify whether additional files must be read or changed.
7. Report whether the initial assumptions were sufficient.

Do not assume the listed files are sufficient.


## Task

Design a focused implementation plan for the requested change.

Do not modify files yet unless explicitly asked.

## Plan requirements

Include:

- current behavior
- desired behavior
- affected layers
- files likely to change
- files inspected but not changed
- out-of-scope layers
- test plan
- rollout or migration concerns
- risks and alternatives

## Output

```text
Current behavior:
- ...

Proposed design:
- ...

Likely change targets:
- ...

Out of scope:
- ...

Test plan:
- ...

Risks:
- ...

Implementation steps:
1. ...
2. ...
3. ...
```
