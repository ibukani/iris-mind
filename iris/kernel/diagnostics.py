"""Kernel 全体の状態スナップショットとヘルスチェック。

各 plugin (io/memory/agency) は `get_state()` または `health()` メソッドを公開する。
`SystemDiagnostics` は `attach_layer_providers` 経由でそれらを受け取り、
ツリー状の state 取得・履歴クエリ・レポート生成を提供する。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class _StateLike(Protocol):
    def get_state(self) -> dict[str, Any]: ...


@runtime_checkable
class _HealthLike(Protocol):
    def health(self) -> str: ...


def _resolve_path(tree: dict, path: str) -> Any:
    if not path:
        return tree
    keys = path.split(".")
    current: Any = tree
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current


def _flatten(tree: dict, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in tree.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        else:
            result[key] = v
    return result


class SystemDiagnostics:
    """Kernel / 各層の state を集約し、ツリー状のクエリとレポートを提供する。"""

    def __init__(
        self,
        event_bus: object | None = None,
        tracer: object | None = None,
        kernel: object | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._tracer = tracer
        self._kernel = kernel
        self._layer_providers: dict[str, object] = {}

    def attach_layer_providers(self, providers: dict[str, object]) -> None:
        """各 layer の state/health を提供するオブジェクトを後から登録する。"""
        self._layer_providers.update(providers)

    def _layer_objects(self) -> Iterator[tuple[str, Any]]:
        yield from self._layer_providers.items()

    def get_state(self) -> dict[str, Any]:
        tree: dict[str, Any] = {}
        for name, obj in self._layer_objects():
            if obj is None:
                continue
            if hasattr(obj, "get_state"):
                try:
                    tree[name] = obj.get_state()
                except Exception as e:
                    logger.debug("SystemDiagnostics: get_state failed for {}", name)
                    tree[name] = {"error": str(e)}
            else:
                tree[name] = {"error": "no get_state"}
        if self._kernel is not None and hasattr(self._kernel, "get_state"):
            try:
                from typing import cast

                tree["kernel"] = cast(_StateLike, self._kernel).get_state()
            except Exception as e:
                tree["kernel"] = {"error": str(e)}
        if self._tracer is not None:
            tree["eventbus"] = {
                "subscribers": getattr(self._tracer, "subscriber_count", 0),
                "total_published": getattr(self._tracer, "publish_count", 0),
                "errors": getattr(self._tracer, "error_count", 0),
            }
        return tree

    def query(self, path: str, history: bool = False, n: int = 10) -> Any:
        if history:
            return self._query_history(path, n)
        return _resolve_path(self.get_state(), path)

    def _query_history(self, path: str, n: int = 10) -> list[dict[str, Any]] | None:
        if self._tracer is None:
            return None
        find = getattr(self._tracer, "find", None)
        if find is None:
            return None
        result = find(category=path, n=n)
        return list(result) if result else None

    def health(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, obj in self._layer_objects():
            if obj is None:
                result[name] = "NOT_LOADED"
            elif hasattr(obj, "health"):
                try:
                    result[name] = obj.health()
                except Exception as e:
                    result[name] = f"ERROR: {e}"
            else:
                result[name] = "OK (no health check)"
        if self._tracer is not None:
            err = getattr(self._tracer, "error_count", 0)
            pub = getattr(self._tracer, "publish_count", 0)
            result["eventbus"] = f"OK (published={pub}, errors={err})" if err == 0 else f"WARN: {err} errors"
        return result

    def generate_report(self) -> str:
        state = self.get_state()
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Iris Debug Report",
            f"**Generated**: {dt}",
            "",
        ]

        flat = _flatten(state)
        lines.append("## State Summary")
        for k, v in flat.items():
            lines.append(f"- **{k}**: {v}")

        h = self.health()
        lines.extend(["", "## Health"])
        for k, v in h.items():
            lines.append(f"- **{k}**: {v}")

        if self._tracer is not None:
            recent: list[dict[str, Any]] = list(getattr(self._tracer, "recent", lambda n: [])(5))
            lines.extend(["", "## Recent Events (last 5)"])
            for e in recent:
                ts = e.get("timestamp", "")
                et = e.get("type", "")
                src = e.get("source", "")
                cat = e.get("category", "")
                extra = f" [{cat}]" if cat else ""
                lines.append(f"- [{ts}] {et} <{src}>{extra}")

        return "\n".join(lines)


__all__ = ["SystemDiagnostics"]
