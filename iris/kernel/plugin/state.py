from __future__ import annotations

from typing import Any

from loguru import logger


class KernelState:
    def __init__(self) -> None:
        self._layer_states: dict[str, str] = {}
        self._shutdown_requested = False

    @property
    def global_state(self) -> str:
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
        return dict(self._layer_states)

    def set_layer_state(self, layer: str, state: str) -> None:
        old = self._layer_states.get(layer)
        self._layer_states[layer] = state
        if old != state:
            logger.info("KernelState: {} state {} -> {} (global={})", layer, old or "NONE", state, self.global_state)

    def get_state(self) -> dict[str, Any]:
        return {
            "global_state": self.global_state,
            "layer_states": dict(self._layer_states),
            "shutdown_requested": self._shutdown_requested,
        }

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        logger.info("KernelState: shutdown requested")
