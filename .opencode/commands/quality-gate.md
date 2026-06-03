---
description: Run a final quality check for the current diff.
---

@quality-gate

Quality gate target: `$1`

Check the current diff or specified target before considering the work complete.

## Check

- scope
- v1.2.1 responsibility boundaries
- stale compatibility code
- PluginManager/EventBus compatibility shims
- service locator / global registry additions
- test quality
- documentation consistency
- validation results
