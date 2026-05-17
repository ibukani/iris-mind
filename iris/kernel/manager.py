from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class KernelManager:
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
        self._layer_states[layer] = state

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
