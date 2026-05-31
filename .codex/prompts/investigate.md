# Codex Prompt: Investigate

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

Investigate the requested behavior, bug, design question, or code area.

Do not modify files unless explicitly asked.

## Output

```text
Question / target:
- ...

Initial investigation targets:
- ...

Additional files inspected:
- ...

Findings:
- ...

Relevant call paths:
- ...

Tests or validation found:
- ...

Risks / unknowns:
- ...

Recommended next action:
- ...
```
