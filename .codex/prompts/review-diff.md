# Codex Prompt: Review Current Diff

Read `AGENTS.md` first.

## Task

Review the current diff. Do not modify code unless explicitly asked.

## Discovery requirement

Treat changed files as the initial hypothesis, not the complete review scope.

Before reviewing:

1. Inspect the current diff.
2. Search references for changed public functions/classes.
3. Inspect related tests.
4. Check whether the change crosses layer boundaries.
5. Check whether any caller, config path, or entrypoint was missed.

## Review criteria

- Does the change follow `AGENTS.md`?
- Is the change limited to the requested scope?
- Are layer boundaries preserved?
- Did provider-specific logic leak into execution/memory/limbic?
- Did protobuf concerns leak outside transport?
- Did managers/gateways/orchestrators become too large?
- Are there unnecessary compatibility layers?
- Is any dead code left behind?
- Are tests sufficient?
- Are validation commands reported honestly?

## Output

```text
Summary:
- ...

Critical issues:
- ...

Medium issues:
- ...

Minor issues:
- ...

Missing tests:
- ...

Suggested fix order:
1. ...
2. ...
3. ...
```
