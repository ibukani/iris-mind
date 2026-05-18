from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class KernelManager:
    """カーネル状態集約。全層の動作状態を一元管理し、graceful shutdown を制御する。

    脳科学のアナロジー：
        - 脳幹の視床下部に相当し、全層の状態を監視し、
        - シャットダウン信号を伝播させる。
    """

    def __init__(self) -> None:
        self._layer_states: dict[str, str] = {}
        self._shutdown_requested = False

    @property
    def global_state(self) -> str:
        """全層の状態から推定される システム全体の状態を返す。

        優先度: EXECUTING > DECIDING > SENSING > IDLE

        Returns:
            システムの現在の状態。
        """
        if not self._layer_states:
            return "IDLE"
        if any(s == "EXECUTING" for s in self._layer_states.values()):
            return "EXECUTING"
        if any(s == "DECIDING" for s in self._layer_states.values()):
            return "DECIDING"
        if any(s == "SENSING" for s in self._layer_states.values()):
            return "SENSING"
        return "IDLE"

    @property
    def layer_states(self) -> dict[str, str]:
        """全層の現在の状態を返す（読み取り専用コピー）。

        Returns:
            層名 -> 状態 の辞書。
        """
        return dict(self._layer_states)

    def set_layer_state(self, layer: str, state: str) -> None:
        """指定の層の状態を更新する。

        Args:
            layer: 層の識別子（例: "kernel", "io", "memory"）。
            state: 設定する状態（"IDLE", "SENSING", "DECIDING", "EXECUTING"）。
        """
        self._layer_states[layer] = state

    @property
    def shutdown_requested(self) -> bool:
        """シャットダウン要求の状態を返す。

        Returns:
            True ならシャットダウンが要求されている。
        """
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        """シャットダウンを要求する。

        KernelProcess など、監視側が定期的に確認し、
        graceful shutdown を実施する。
        """
        self._shutdown_requested = True
