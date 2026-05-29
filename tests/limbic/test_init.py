from __future__ import annotations

from iris.limbic import MANIFEST, plugin


class TestLimbicPlugin:
    def test_manifest(self) -> None:
        assert MANIFEST.name == "limbic"
        assert MANIFEST.version == "0.1.0"
        assert MANIFEST.dependencies == {"EventBus"}

    def test_plugin_instance(self) -> None:
        assert plugin is not None
        assert hasattr(plugin, "init")
        assert hasattr(plugin, "start")
        assert hasattr(plugin, "stop")
