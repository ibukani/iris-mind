from __future__ import annotations

from types import ModuleType

from iris.kernel.plugin.manifest import PluginManifest, PluginState


class PluginInstance:
    __slots__ = ("manifest", "module", "state")

    def __init__(self, manifest: PluginManifest, module: ModuleType | None) -> None:
        self.manifest = manifest
        self.module = module
        self.state = PluginState.UNLOADED
