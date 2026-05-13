import subprocess
import sys

from iris.capabilities.registry import CapabilityRegistry

_BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "format",
    "dd if=",
    ":(){ :|:& };:",
    "wget ",
    "curl ",
    "nc ",
    "netcat",
    "chmod 777",
    "chown ",
    "> /dev/sda",
    "> /dev/",
    "| sh",
    "| bash",
    "| cmd",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
]
_BLOCKED_PATTERNS = [
    r"rm\s+(-rf?\s+)?[/~]",
    r"mkfs\.\w+",
    r"dd\s+if=",
    r"wget\s+\w+\.\w+",
    r"curl\s+\w+\.\w+",
    r"chmod\s+777",
    r"chown\s",
]


def _is_dangerous(command: str) -> str | None:
    cmd_lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"blocked: '{blocked}' is not allowed"
    import re

    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return f"blocked: pattern '{pattern}' matched"
    return None


def register(registry: CapabilityRegistry):
    @registry.register_func(
        name="run_python",
        description="指定されたPythonコードを隔離サブプロセスで実行します",
        allowed_roles={"smart"},
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
        description="指定されたシェルコマンドを実行します（危険コマンドはブロックされます）",
        allowed_roles={"smart"},
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
        blocked = _is_dangerous(command)
        if blocked:
            return f"Error: {blocked}"
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
