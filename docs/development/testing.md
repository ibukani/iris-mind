# Testing & Code Quality

## Running tests

```bash
# All tests
uv run pytest tests/

# Quick run (short traceback)
uv run pytest tests/ -q

# Architecture guards only
uv run pytest tests/architecture -q

# Specific test file
uv run pytest tests/runtime/test_cli.py -q
```

## Code quality

```bash
# Lint check
uv run ruff check .

# Lint auto-fix
uv run ruff check --fix .

# Format check
uv run ruff format --check .

# Format
uv run ruff format .

# Type check
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
```

## Target-only test suite

All tests verify the current target architecture only. There is no legacy test suite.

### Architecture guards (`tests/architecture/`)

| File | Purpose |
|------|---------|
| `test_target_architecture_guards.py` | Legacy package absence, forbidden symbols, layer dependency direction, runtime entrypoint rules, `__init__.py` rules, no service locator, test-suite target-only verification |
| `test_cognitive_runtime_boundaries.py` | Layer boundary rules and legacy quarantine |
| `test_cognitive_runtime_anti_patterns.py` | Anti-pattern scans (global mutable registries, untyped contracts, etc.) |
| `test_cognitive_runtime_contracts.py` | Design contract tests (frozen dataclasses, FrameBuilder, PipelineStep) |

These tests enforce that deleted legacy systems are not reintroduced and that package boundaries remain clean.
