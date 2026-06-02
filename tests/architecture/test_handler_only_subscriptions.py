"""EventBus 購読が handler.py 以外で発生していないことを検証するアーキテクチャテスト。

manager.py / orchestrator.py / gateway.py / builder.py などのロジック / 組み立て系
ファイルが EventBus.subscribe を直接呼ぶことを禁止する。購読は handler.py
(または handlers) に集約する。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "iris"

ALLOWED_SUBSCRIBE_FILES = {"handler.py", "handlers.py"}


def _iter_python_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def _calls_subscribe(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        names: list[str] = []
        cur: ast.AST | None = func
        while isinstance(cur, ast.Attribute):
            names.insert(0, cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            names.insert(0, cur.id)
        if not names:
            continue
        if names[-1] != "subscribe":
            continue
        if "bus" in names or "event_bus" in names:
            return True
    return False


def test_handler_only_subscriptions() -> None:
    violations: list[str] = []
    for path in _iter_python_files(ROOT):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if not parts:
            continue
        if parts[-1] in ALLOWED_SUBSCRIBE_FILES:
            continue
        if parts[0] == "kernel" and parts[-1] == "factory.py":
            continue
        if not _calls_subscribe(path):
            continue
        violations.append(str(rel))
    assert not violations, (
        f"EventBus.subscribe must only be called in handler.py / handlers.py. Violations: {violations}"
    )
