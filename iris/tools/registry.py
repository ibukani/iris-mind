from __future__ import annotations

from collections.abc import Callable
import logging
from pathlib import Path

from iris.tools.decorator import get_tool_def, register_decorated_tools
from iris.tools.models import ToolDef

logger = logging.getLogger(__name__)
_DEFAULT_ALLOWED_ROLES = {"base", "smart"}


class ToolRegistry:
    """ツール（capability）の登録・検索・実行を管理するレジストリ。

    ツールは @tool デコレータで定義され、register_decorated() で登録される。
    LLM から tool_calls で呼び出された際に execute() で実行される。
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        """ツール定義を登録する。

        Args:
            tool_def: ToolDef インスタンス。
        """
        self._tools[tool_def.name] = tool_def

    def register_decorated(self, fn: Callable) -> None:
        """@tool デコレータ付き関数をツールとして登録する。

        Args:
            fn: @tool デコレータで装飾された関数。

        Raises:
            ValueError: 関数が @tool デコレータで装飾されていない場合。
        """
        td = get_tool_def(fn)
        if td is None:
            raise ValueError("Function has no _tool_def. Use @tool decorator.")
        self.register(td)

    def get(self, name: str) -> ToolDef | None:
        """名前でツール定義を検索する。

        Args:
            name: ツール名。

        Returns:
            ToolDef、またはなければ None。
        """
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """全ツールを OpenAI JSON スキーマ形式で返す。

        Returns:
            ツール定義のリスト（OpenAI tool_choice 互換フォーマット）。
        """
        return [t.to_openai_tool() for t in self._tools.values()]

    def list_tools_for_role(self, role: str) -> list[dict]:
        """指定のロール（モデル役割）で使用可能なツールを返す。

        Args:
            role: モデルロール（例: "base", "smart"）。

        Returns:
            ツール定義のリスト。
        """
        return [t.to_openai_tool() for t in self._tools.values() if role in (t.allowed_roles or _DEFAULT_ALLOWED_ROLES)]

    def execute(self, name: str, **kwargs: object) -> str:
        """ツールを実行する。

        Args:
            name: ツール名。
            **kwargs: ツールへのキーワード引数。

        Returns:
            ツール実行結果（文字列）。エラー時はエラーメッセージ。
        """
        td = self.get(name)
        if td is None:
            return f"Error: tool '{name}' not found"
        return td.execute(**kwargs)

    def is_side_effect(self, name: str) -> bool:
        """ツールが副作用型（結果を会話に戻さない）かを判定する。

        Args:
            name: ツール名。

        Returns:
            副作用型ならば True。
        """
        td = self.get(name)
        return td is not None and td.side_effect

    def discover_modules(self, base_paths: list[str] | None = None) -> None:
        """指定パス配下のツールモジュールを動的に読み込む。

        各モジュールは register(registry) 関数をエクスポートする。

        Args:
            base_paths: ツールモジュールのベースパス（デフォルト: ["iris/tools/builtins"]）。
        """
        if base_paths is None:
            base_paths = ["iris/tools/builtins"]

        import importlib

        for base in base_paths:
            base_path = Path(base).resolve()
            if not base_path.is_dir():
                continue
            base_module = base.replace("/", ".").replace("\\", ".")
            for module_file in self._iter_tool_modules(base_path):
                module_path = self._module_path(base_module, base_path, module_file)
                try:
                    module = importlib.import_module(module_path)
                    register = getattr(module, "register", None)
                    if callable(register):
                        register(self)
                    else:
                        register_decorated_tools(module, self)
                except Exception as exc:
                    logger.warning("Failed to load tool module %s: %s", module_path, exc)

    def _iter_tool_modules(self, base_path: Path) -> list[Path]:
        return [path for path in base_path.rglob("server.py") if path.is_file()]

    def _module_path(self, base_module: str, base_path: Path, module_file: Path) -> str:
        relative_module = module_file.relative_to(base_path).with_suffix("")
        return ".".join([base_module, *relative_module.parts])
