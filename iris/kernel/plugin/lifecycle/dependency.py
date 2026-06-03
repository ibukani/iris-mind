from __future__ import annotations

from graphlib import TopologicalSorter

from loguru import logger

from iris.kernel.plugin.manifest import PluginPhase

from .models import PluginInstance


class DependencyError(Exception):
    def __init__(self, plugin_name: str, missing: set[str]) -> None:
        self.plugin_name = plugin_name
        self.missing = missing
        super().__init__(f"Plugin '{plugin_name}' has unresolved dependencies: {missing}")


def resolve_order(plugins: dict[str, PluginInstance], builtin_service_names: set[str]) -> list[str]:
    graph: dict[str, set[str]] = {name: set(p.manifest.dependencies) for name, p in plugins.items()}

    known_services: set[str] = set(plugins.keys())
    for p in plugins.values():
        known_services.update(p.manifest.provides)
    known_services.update(builtin_service_names)

    for dep_set in graph.values():
        for dep in dep_set:
            if dep not in known_services:
                raise KeyError(f"Plugin has unresolved dependency '{dep}'")

    phases: dict[PluginPhase, list[str]] = {}
    for name, p in plugins.items():
        phases.setdefault(p.manifest.phase, []).append(name)

    order: list[str] = []
    for phase in sorted(PluginPhase):
        names = phases.get(phase, [])
        if not names:
            continue
        phase_graph = {n: graph[n] for n in names}
        try:
            ts: TopologicalSorter[str] = TopologicalSorter(phase_graph)
            phase_order = list(ts.static_order())
        except Exception:
            logger.exception("PluginLifecycle: cycle detected in phase {}", phase.name)
            raise
        order.extend(name for name in phase_order if name in plugins)

    logger.info(
        "PluginLifecycle: order: {}",
        " → ".join(f"({plugins[n].manifest.phase.name}){n}" for n in order),
    )

    return order


def verify_dependencies(plugins: dict[str, PluginInstance], builtin_service_names: set[str]) -> None:
    known_services: set[str] = set(plugins.keys())
    for p in plugins.values():
        known_services.update(p.manifest.provides)
    known_services.update(builtin_service_names)

    for name, p in plugins.items():
        missing = p.manifest.dependencies - known_services
        if missing:
            raise DependencyError(name, missing)
