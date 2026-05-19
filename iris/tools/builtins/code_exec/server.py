import logging
import re
import subprocess
import sys

from iris.tools.decorator import register_tools, tool
from iris.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

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
            logger.info("CodeExec: blocked command (keyword) cmd=%.100s", command)
            return f"blocked: '{blocked}' is not allowed"
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            logger.info("CodeExec: blocked command (pattern) cmd=%.100s", command)
            return f"blocked: pattern '{pattern}' matched"
    return None


@tool(allowed_roles={"smart"})
def run_python(code: str, timeout: int = 10) -> str:
    """指定されたPythonコードを隔離サブプロセスで実行します"""
    logger.info("CodeExec: run_python (timeout=%d, code_len=%d)", timeout, len(code))
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


@tool(allowed_roles={"smart"})
def run_shell(command: str, timeout: int = 15) -> str:
    """指定されたシェルコマンドを実行します（危険コマンドはブロックされます）"""
    blocked = _is_dangerous(command)
    if blocked:
        return f"Error: {blocked}"
    logger.info("CodeExec: run_shell cmd=%.100s timeout=%d", command, timeout)
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


def register(registry: ToolRegistry) -> None:
    register_tools(registry, run_python, run_shell)
