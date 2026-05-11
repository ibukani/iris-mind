import subprocess
import sys
import tempfile
from pathlib import Path
from capabilities.registry import CapabilityRegistry


def register(registry: CapabilityRegistry):
    @registry.register_func(
        name="run_python",
        description="指定されたPythonコードを隔離サブプロセスで実行します",
        parameters={
            "code": {
                "type": "string",
                "description": "実行するPythonコード",
                "required": True,
            },
            "timeout": {
                "type": "integer",
                "description": "タイムアウト（秒）",
            },
        },
    )
    def run_python(code: str, timeout: int = 10) -> str:
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output = f"Exit code: {result.returncode}\n{output}"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: execution timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"

    @registry.register_func(
        name="run_shell",
        description="指定されたシェルコマンドを実行します",
        parameters={
            "command": {
                "type": "string",
                "description": "実行するコマンド",
                "required": True,
            },
            "timeout": {
                "type": "integer",
                "description": "タイムアウト（秒）",
            },
        },
    )
    def run_shell(command: str, timeout: int = 15) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output = f"Exit code: {result.returncode}\n{output}"
            return (output.strip() or "(no output)")[:2000]
        except subprocess.TimeoutExpired:
            return f"Error: execution timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"
