from __future__ import annotations

from iris.kernel.config import Config, ModelConfig
from iris.kernel.core import KernelProcess


def _dummy_config() -> Config:
    return Config(
        model=ModelConfig(
            models=[{"name": "test", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
            provider="ollama",
            base_url="http://localhost:11434",
        )
    )


def test_kernel_process_shutdown_before_start_does_not_crash() -> None:
    """start() 前に shutdown() を呼んでもクラッシュしない。"""
    kp = KernelProcess.__new__(KernelProcess)
    kp._config = _dummy_config()
    kp._ctx = None
    kp.shutdown()
