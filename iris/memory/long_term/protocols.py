"""互換性のための再エクスポート。
store_protocols.py に移動しました。新しいコードは store_protocols を import してください。"""

from iris.memory.long_term.store_protocols import (
    AgentsMdStoreProtocol,
    EpisodicStoreProtocol,
    SemanticStoreProtocol,
)

__all__ = ["AgentsMdStoreProtocol", "EpisodicStoreProtocol", "SemanticStoreProtocol"]
