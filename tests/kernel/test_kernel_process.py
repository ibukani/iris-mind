from __future__ import annotations

from iris.kernel.config import Config, ModelConfig
from iris.kernel.process import KernelProcess


def _dummy_config() -> Config:
    return Config(
        model=ModelConfig(
            models=[{"name": "test", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        )
    )


def test_kernel_process_shutdown_before_start_does_not_crash() -> None:
    kp = KernelProcess.__new__(KernelProcess)
    kp._config = _dummy_config()
    kp._manager = None
    kp.shutdown()
