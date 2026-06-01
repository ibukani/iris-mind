# OpenCode Agent Settings Notes

## Main Changes

- `opencode.json` now loads only `AGENTS.md` as the always-on instruction file.
- Existing agents were tightened around:
  - falsification-oriented investigation
  - responsibility boundaries
  - test trust policy
  - deletion of obsolete compatibility code
  - Japanese completion reports
- Added agents:
  - `refactorer`: scoped structural refactoring with test/doc updates
  - `test-auditor`: test cleanup for stale, duplicate, misleading, and over-specified tests
  - `quality-gate`: final non-editing validation pass
- Added commands:
  - `/refactor`
  - `/audit-tests`
  - `/quality-gate`

## Recommended Use

- Use `/investigate <target>` before large unclear changes.
- Use `/refactor <target>` for structure cleanup.
- Use `/audit-tests <target>` when tests look excessive or block valid refactoring.
- Use `/quality-gate <target>` before accepting a large diff.
