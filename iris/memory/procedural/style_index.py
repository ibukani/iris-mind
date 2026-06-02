"""StyleMemoryIndex — スタイル記憶の検索インデックス抽象。

責務:
- ``StyleMemoryStore.list_enabled()`` の代替・拡張ポイントを定義
- デフォルト実装 ``MetadataFilterStyleIndex`` は現行のメタデータフィルタと同じ挙動
- ベクトル検索が必要な場合は別実装 (例: ``VectorStyleIndex``) を差し込んで拡張可能
- 検索結果は ``StyleMemory`` インスタンスそのものを返し、``Store`` のメタデータ
  (success_count 等) は呼び出し側がストアから引き直す

設計上の注意:
- ``StyleMemory`` のテキストフィールド (``content`` / ``activation_condition``) は
  短く要点のみ。埋め込み生成コストが見合わないため、デフォルトはメタデータフィルタ。
- ただし「テーマや雰囲気のような曖昧一致が要る」要件が出てきた場合にベクトル実装を
  差し込めるよう Protocol だけを先に用意する。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from iris.memory.procedural.models import StyleMemory

if TYPE_CHECKING:
    from iris.memory.procedural.style_store import StyleMemoryStore


@runtime_checkable
class StyleMemoryIndex(Protocol):
    """StyleMemory を検索するためのインデックス抽象。"""

    def search(
        self,
        *,
        query: str = "",
        account_id: str = "",
        room_id: str = "",
        max_items: int = 8,
    ) -> list[StyleMemory]:
        """``query`` (空なら純粋なメタデータフィルタ) で検索し、関連順に最大 ``max_items`` 返す。"""
        ...


class MetadataFilterStyleIndex:
    """``StyleMemoryStore.list_enabled()`` の動作を ``StyleMemoryIndex`` として再公開する実装。

    注意点: 検索時に ``Store.list_all()`` を毎回スキャンするため、データ量に比例して
    O(N) で遅くなる。StyleMemory は原則 1 アカウントあたり数十件を想定しているため
    実用上は問題ないが、ベクトルインデックスが必要になった場合は別実装に差し替える。
    """

    def __init__(self, store: StyleMemoryStore) -> None:
        self._store = store

    def search(
        self,
        *,
        query: str = "",
        account_id: str = "",
        room_id: str = "",
        max_items: int = 8,
    ) -> list[StyleMemory]:
        del query
        return self._store.list_enabled(
            account_id=account_id,
            room_id=room_id,
            max_items=max_items,
        )


__all__ = ["MetadataFilterStyleIndex", "StyleMemoryIndex"]
