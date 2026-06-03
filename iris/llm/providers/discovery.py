"""Discovery — LLM プロバイダモジュールの自動発見。

providers/ 配下の .py ファイルを import し、
__init_subclass__ による auto-registration をトリガーする。
変更理由: base.py から発見ロジックを分離。
"""

from __future__ import annotations


def discover_providers() -> None:
    """providers/ 配下の全プロバイダモジュールを自動発見し import する。

    各モジュールのクラス定義時に __init_subclass__ が呼ばれ、
    provider_name をキーに自動登録される。
    追加ファイルを置くだけで既存コード編集は不要。
    """
    import importlib
    from pathlib import Path

    pkg_path = Path(__file__).parent
    for f in sorted(pkg_path.glob("*.py")):
        name = f.stem
        if name in ("base", "__init__", "registry", "discovery"):
            continue
        importlib.import_module(f".{name}", "iris.llm.providers")
