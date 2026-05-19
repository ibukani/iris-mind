import logging
from pathlib import Path
import subprocess
import sys

from iris.tools.decorator import register_tools, tool
from iris.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@tool(allowed_roles={"smart"})
def generate_capability(name: str, code: str) -> str:
    """新しいcapabilityコードを生成し、tools/builtins に保存します"""
    dest = Path("iris/tools/builtins") / name / "server.py"
    if dest.exists():
        logger.info("SelfMod: generate_capability %s FAILED (already exists)", name)
        return f"Error: already exists: {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    (dest.parent / "__init__.py").touch()
    dest.write_text(code, encoding="utf-8")
    result = _sandbox_test(dest)
    if result["ok"]:
        logger.info("SelfMod: generated capability %s at %s", name, dest)
        return f"Created: {dest}\nSandbox test passed"
    dest.unlink(missing_ok=True)
    logger.info("SelfMod: generate_capability %s FAILED (sandbox test)", name)
    return f"Sandbox test failed: {result['error']}"


@tool(allowed_roles={"smart"})
def modify_file(path: str, new_content: str) -> str:
    """既存ファイルを変更します（差分表示前提）"""
    fp = Path(path)
    if not fp.exists():
        return f"Error: file not found: {path}"
    old = fp.read_text(encoding="utf-8")
    fp.write_text(new_content, encoding="utf-8")
    logger.info("SelfMod: modified %s (%d -> %d bytes)", path, len(old), len(new_content))
    return f"Modified: {path} ({len(old)} \u2192 {len(new_content)} bytes)"


@tool(allowed_roles={"smart"})
def sandbox_test(path: str) -> str:
    """指定されたPythonファイルの構文チェックとテスト実行を行います"""
    result = _sandbox_test(Path(path))
    return "OK" if result["ok"] else f"FAIL: {result['error']}"


def _sandbox_test(filepath: Path) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import py_compile; py_compile.compile({str(filepath)!r}, doraise=True)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "error": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def register(registry: ToolRegistry) -> None:
    register_tools(registry, generate_capability, modify_file, sandbox_test)
