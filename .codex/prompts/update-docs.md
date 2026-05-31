# Codex Prompt: Update Documentation

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

Update documentation for the requested change.

## Rules

- Prefer implementation over outdated documentation.
- Do not invent behavior.
- Do not document future features as current behavior.
- Update only documents related to the change.
- If code and docs conflict, report the conflict.

## Output

```text
Updated docs:
- ...

Behavior documented:
- ...

Unresolved inconsistencies:
- ...
```
