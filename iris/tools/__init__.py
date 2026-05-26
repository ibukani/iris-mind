from __future__ import annotations

from typing import TYPE_CHECKING

from iris.kernel.plugin import PluginCategory, PluginManifest, PluginPhase, PluginProtocol
from iris.tools.decorator import get_tool_def, register_decorated_tools, register_tools, tool
from iris.tools.models import ToolDef, ToolResult
from iris.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager

MANIFEST = PluginManifest(
    name="tools",
    version="0.1.0",
    category=PluginCategory.TOOL,
    phase=PluginPhase.CORE,
    dependencies=set(),
    provides=["ToolRegistry", "ToolEngine"],
    description="ツールシステム",
)


class ToolsPlugin:
    MANIFEST = MANIFEST

    def init(self, manager: PluginManager) -> None:
        manager.register_manifest(MANIFEST)

        registry = ToolRegistry()
        registry.discover_modules()

        from iris.agency.execution.engine import ToolEngine

        tool_exec = ToolEngine(registry=registry)

        manager.provide(ToolRegistry, registry)
        manager.provide(ToolEngine, tool_exec)

    def start(self, manager: PluginManager) -> None:
        pass

    def stop(self, manager: PluginManager) -> None:
        pass


plugin: PluginProtocol = ToolsPlugin()

__all__ = [
    "ToolDef",
    "ToolRegistry",
    "ToolResult",
    "get_tool_def",
    "register_decorated_tools",
    "register_tools",
    "tool",
]
