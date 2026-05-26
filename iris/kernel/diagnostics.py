from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iris.agency import AgencyManager
    from iris.event.event_bus import EventBus
    from iris.event.tracer import EventTracer
    from iris.io.manager import IOManager
    from iris.kernel.manager import KernelManager
    from iris.limbic.manager import LimbicManager
    from iris.memory.manager import MemoryManager


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


_LAYER_NAMES = ("kernel", "io", "memory", "limbic", "agency")


class SystemDiagnostics:
    def __init__(
        self,
        event_bus: EventBus | None = None,
        tracer: EventTracer | None = None,
        kernel: KernelManager | None = None,
        io: IOManager | None = None,
        memory: MemoryManager | None = None,
        limbic: LimbicManager | None = None,
        agency: AgencyManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._tracer = tracer
        self._kernel = kernel
        self._io = io
        self._memory = memory
        self._limbic = limbic
        self._agency = agency

    def _layer_objects(self) -> Iterator[tuple[str, Any]]:
        for name in _LAYER_NAMES:
            yield name, getattr(self, f"_{name}")

    def get_state(self) -> dict[str, Any]:
        tree: dict[str, Any] = {}
        for name, obj in self._layer_objects():
            if obj is not None and hasattr(obj, "get_state"):
                try:
                    tree[name] = obj.get_state()
                except Exception:
                    tree[name] = {"error": "get_state failed"}
            elif obj is not None:
                tree[name] = {"error": "no get_state"}
        if self._tracer is not None:
            tree["eventbus"] = {
                "subscribers": self._tracer.subscriber_count,
                "total_published": self._tracer.publish_count,
                "errors": self._tracer.error_count,
            }
        return tree

    def query(self, path: str, history: bool = False, n: int = 10) -> Any:
        if history:
            return self._query_history(path, n)
        return _resolve_path(self.get_state(), path)

    def _query_history(self, path: str, n: int = 10) -> list[dict[str, Any]] | None:
        if self._tracer is None:
            return None
        return self._tracer.find(category=path, n=n)

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
            err = self._tracer.error_count
            result["eventbus"] = (
                f"OK (published={self._tracer.publish_count}, errors={err})" if err == 0 else f"WARN: {err} errors"
            )
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
            recent = self._tracer.recent(5)
            lines.extend(["", "## Recent Events (last 5)"])
            for e in recent:
                ts = e.get("timestamp", "")
                et = e.get("type", "")
                src = e.get("source", "")
                cat = e.get("category", "")
                extra = f" [{cat}]" if cat else ""
                lines.append(f"- [{ts}] {et} <{src}>{extra}")

        return "\n".join(lines)
