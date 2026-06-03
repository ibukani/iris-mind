---
description: Review the current diff. Code changes are usually forbidden.
---

@reviewer

Review the current diff.

## Review Points

- Is the change scope appropriate?
- Are layer boundaries preserved?
- Did provider-specific behavior leak into upper layers?
- Did protobuf dependency leak into domain code?
- Are managers / gateways / orchestrators growing too large?
- Are there unnecessary compatibility layers or dead code?
- Are tests sufficient and behavior-focused?
- Were stale or misleading tests preserved?
- Are validation results reported honestly?
