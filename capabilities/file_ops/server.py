from pathlib import Path

from capabilities.registry import CapabilityRegistry


def register(registry: CapabilityRegistry):
    @registry.register_func(
        name="read_file",
        description="指定されたファイルの内容を読み込みます",
        allowed_roles={"base", "smart"},
        parameters={
            "path": {
                "type": "string",
                "description": "読み込むファイルのパス",
                "required": True,
            }
        },
    )
    def read_file(path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        return p.read_text(encoding="utf-8")

    @registry.register_func(
        name="write_file",
        description="指定されたファイルに内容を書き込みます（既存ファイルは上書き）",
        allowed_roles={"base", "smart"},
        parameters={
            "path": {"type": "string", "description": "書き込むファイルのパス", "required": True},
            "content": {"type": "string", "description": "書き込む内容", "required": True},
        },
    )
    def write_file(path: str, content: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written: {path} ({len(content)} bytes)"

    @registry.register_func(
        name="list_files",
        description="指定されたディレクトリ内のファイル一覧を返します",
        allowed_roles={"base", "smart"},
        parameters={
            "path": {
                "type": "string",
                "description": "ディレクトリのパス（省略時はカレント）",
            }
        },
    )
    def list_files(path: str = ".") -> str:
        p = Path(path)
        if not p.is_dir():
            return f"Error: not a directory: {path}"
        files = [str(f.relative_to(p)) for f in p.rglob("*") if f.is_file()]
        if not files:
            return "(empty)"
        truncated = len(files) > 200
        result = "\n".join(files[:200])
        if truncated:
            result += f"\n... and {len(files) - 200} more files"
        return result
