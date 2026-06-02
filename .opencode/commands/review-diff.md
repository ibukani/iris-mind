---
description: Review the current diff. Code changes are usually forbidden.
---

@reviewer

Review the current diff.

## Review Points

- Is the change scope appropriate?
- Are v1.2.1 responsibility boundaries preserved when migration code is touched?
- Did provider-specific behavior leak into cognitive/domain layers?
- Did protobuf / gRPC / external app SDK dependency leak into cognitive/domain code?
- Are managers / gateways / orchestrators growing too large?
- Are there unnecessary compatibility layers or dead code?
- Were PluginManager/EventBus compatibility shims added without explicit request?
- Are service locator, global registry, or string-action dispatcher paths added?
- Are tests sufficient and behavior-focused?
- Were stale or misleading tests preserved?
- Are validation results reported honestly?
