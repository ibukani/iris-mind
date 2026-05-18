from __future__ import annotations

import logging
from pathlib import Path

from iris.tools.decorator import register_tools, tool

logger = logging.getLogger(__name__)


@tool(
    side_effect=True,
    allowed_roles={"base", "smart"},
    descriptions={
        "destination": "出力先 (cli=画面出力用、file=ファイル保存用)",
        "content": "送信するテキスト内容",
    },
)
def output_to(destination: str, content: str) -> str:
    """AI が出力先を明示的に選択します。テキストを指定された出力先に送信します。"""
    if destination == "file":
        path = Path("iris_output.txt")
        with path.open("a", encoding="utf-8") as f:
            f.write(content + "\n")
        logger.info("output_to file: %s (%d chars)", path, len(content))
    elif destination != "cli":
        logger.warning("output_to: unknown destination '%s'", destination)
    return f"sent to {destination}"


def register(registry):
    register_tools(registry, output_to)
