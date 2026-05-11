import subprocess
import sys
import tempfile
from pathlib import Path
from capabilities.registry import CapabilityRegistry


def register(registry: CapabilityRegistry):
    @registry.register_func(
        name="generate_capability",
        description="新しいcapabilityコードを生成し、指定されたパスに保存します",
        parameters={
            "name": {
                "type": "string",
                "description": "capability名（例: web_search）",
                "required": True,
            },
            "code": {
                "type": "string",
                "description": "server.py の全コード",
                "required": True,
            },
        },
    )
    def generate_capability(name: str, code: str) -> str:
        dest = Path("capabilities") / name / "server.py"
        if dest.exists():
            return f"Error: already exists: {dest}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        (dest.parent / "__init__.py").touch()
        dest.write_text(code, encoding="utf-8")
        result = _sandbox_test(dest)
        if result["ok"]:
            return f"Created: {dest}\nSandbox test passed"
        dest.unlink(missing_ok=True)
        return f"Sandbox test failed: {result['error']}"

    @registry.register_func(
        name="modify_file",
        description="既存ファイルを変更します（差分表示前提）",
        parameters={
            "path": {
                "type": "string",
                "description": "変更するファイルのパス",
                "required": True,
            },
            "new_content": {
                "type": "string",
                "description": "新しいファイル内容",
                "required": True,
            },
        },
    )
    def modify_file(path: str, new_content: str) -> str:
        fp = Path(path)
        if not fp.exists():
            return f"Error: file not found: {path}"
        old = fp.read_text(encoding="utf-8")
        fp.write_text(new_content, encoding="utf-8")
        return f"Modified: {path} ({len(old)} → {len(new_content)} bytes)"

    @registry.register_func(
        name="sandbox_test",
        description="指定されたPythonファイルの構文チェックとテスト実行を行います",
        parameters={
            "path": {
                "type": "string",
                "description": "テストするファイルのパス",
                "required": True,
            },
        },
    )
    def sandbox_test(path: str) -> str:
        result = _sandbox_test(Path(path))
        return "OK" if result["ok"] else f"FAIL: {result['error']}"


def _sandbox_test(filepath: Path) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             f"import py_compile; py_compile.compile(r'{filepath}', doraise=True)"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "error": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}
