from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.kernel.manager import PluginManager


class PluginProtocol(ABC):
    @abstractmethod
    def init(self, manager: PluginManager) -> None: ...

    @abstractmethod
    def start(self, manager: PluginManager) -> None: ...

    @abstractmethod
    def stop(self, manager: PluginManager) -> None: ...

    def on_config_loaded(self, manager: PluginManager) -> None:
        """全プラグインの init 完了後に呼ばれる。設定の最終確認に使用。"""
        return

    def on_all_ready(self, manager: PluginManager) -> None:
        """全プラグインの start 完了後に呼ばれる。遅延初期化に使用。"""
        return

    def on_pre_shutdown(self, manager: PluginManager) -> None:
        """シャットダウン前に呼ばれる。リソース解放の前に実行。"""
        return
