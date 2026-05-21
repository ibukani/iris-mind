import logging
from pathlib import Path

from iris.tools.decorator import register_tools, tool
from iris.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@tool(allowed_roles={"smart"})
def read_file(path: str) -> str:
    """指定パスのファイルを読み込み、テキスト内容を返します。"""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    return p.read_text(encoding="utf-8")


@tool(allowed_roles={"smart"})
def write_file(path: str, content: str) -> str:
    """指定パスにテキストを書き込みます。親ディレクトリが存在しない場合は作成します。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    logger.info("FileOps: wrote %s (%d bytes)", path, len(content))
    return f"Written: {path} ({len(content)} bytes)"


@tool(allowed_roles={"smart"})
def list_files(path: str = ".") -> str:
    """指定ディレクトリ配下のファイル一覧を返します。"""
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


def register(registry: ToolRegistry) -> None:
    register_tools(registry, read_file, write_file, list_files)
