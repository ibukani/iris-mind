from __future__ import annotations

from iris.kernel.core import KernelProcess


def test_kernel_process_shutdown_before_start_does_not_crash() -> None:
    """start() 前に shutdown() を呼んでもクラッシュしない。"""
    kp = KernelProcess.__new__(KernelProcess)
    kp._config = None
    kp._ctx = None
    kp._output_bridge = None
    kp._input_bridge = None
    kp.shutdown()


def test_kernel_process_stop_bridge_unknown_side_does_not_crash() -> None:
    """存在しない side 名で stop_bridge() を呼んでもクラッシュしない。"""
    kp = KernelProcess.__new__(KernelProcess)
    kp._config = None
    kp._ctx = None
    kp._output_bridge = None
    kp._input_bridge = None
    kp.stop_bridge("invalid")
