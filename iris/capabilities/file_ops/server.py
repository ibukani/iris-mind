from pathlib import Path

from iris.tools.decorator import tool


@tool(allowed_roles={"base", "smart"})
def read_file(path: str) -> str:
    """指定されたファイルの内容を読み込みます"""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    return p.read_text(encoding="utf-8")


@tool(allowed_roles={"base", "smart"})
def write_file(path: str, content: str) -> str:
    """指定されたファイルに内容を書き込みます（既存ファイルは上書き）"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written: {path} ({len(content)} bytes)"


@tool(allowed_roles={"base", "smart"})
def list_files(path: str = ".") -> str:
    """指定されたディレクトリ内のファイル一覧を返します"""
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


def register(registry):
    registry.register_decorated(read_file)
    registry.register_decorated(write_file)
    registry.register_decorated(list_files)
