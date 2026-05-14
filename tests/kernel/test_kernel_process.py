from __future__ import annotations

from iris.kernel.kernel_process import KernelProcess


class _FakeConfig:
    class model:  # noqa: N801
        provider = "ollama"

    class memory:  # noqa: N801
        pass

    class proactive:  # noqa: N801
        check_interval_sec = 60
        min_interval = 300
        scoring_interval = 300
        cooldown = 300

    class logging:  # noqa: N801
        level = "WARNING"
        file = ""

    class personality:  # noqa: N801
        name = "test"


def test_kernel_process_terminate_none_does_not_crash() -> None:
    KernelProcess._terminate_proc(None)


def test_kernel_process_terminate_invalid_proc_does_not_crash() -> None:
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    proc.kill()
    proc.wait()
    KernelProcess._terminate_proc(proc)
