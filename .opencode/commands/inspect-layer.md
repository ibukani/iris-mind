---
description: Inspect responsibilities, dependencies, and boundaries of the specified layer. Code changes are forbidden.
---

@architect

Layer: `$1`

Investigate the specified layer without changing code.

## Investigation Items

- Current responsibilities
- Target v1.2.1 responsibility, if this layer is part of migration
- Main files
- import / call graph
- Related tests
- Boundaries with other layers
- Mixed responsibilities
- Oversized managers / gateways / orchestrators
- Legacy Plugin/EventBus assumptions
- Best next improvement target

## Output

- Current state
- Problems
- Boundary risks
- Improvement candidates
- Minimum implementation steps
