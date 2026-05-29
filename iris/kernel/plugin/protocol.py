from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


@runtime_checkable
class PluginProtocol(Protocol):
    def init(self, manager: PluginManager) -> None: ...

    def start(self, manager: PluginManager) -> None: ...

    def stop(self, manager: PluginManager) -> None: ...

    def on_config_loaded(self, manager: PluginManager) -> None:
        """全プラグインの init 完了後に呼ばれる。設定の最終確認に使用。"""
        ...

    def on_all_ready(self, manager: PluginManager) -> None:
        """全プラグインの start 完了後に呼ばれる。遅延初期化に使用。"""
        ...

    def on_pre_shutdown(self, manager: PluginManager) -> None:
        """シャットダウン前に呼ばれる。リソース解放の前に実行。"""
        ...
