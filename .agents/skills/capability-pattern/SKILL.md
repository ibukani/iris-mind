---
name: capability-pattern
description: Iris capability 追加の全手順を実行するワークフロー
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: iris-extension
---

## What I do

新規 capability（ツール）を Iris に追加する全手順をテンプレート化したものです。
現在の推奨方式は `@tool()` デコレータ（`iris/tools/`）です。`register_func()` による旧方式から移行済み。

## Steps

### 1. Create capability file

以下のテンプレートに従ってファイルを作成する。

#### 推奨: `@tool()` デコレータ（v3.0+）

`capabilities/<name>/server.py` に配置（既存と互換性を維持）：

```python
from iris.tools.decorator import tool


@tool(allowed_roles={"base", "smart"})
def my_tool(param: str) -> str:
    """日本語の説明（この docstring がそのまま description になる）"""
    return f"Result: {param}"
```

**自動生成されるもの**:
- 型ヒント (`str`, `int`, `float`, `bool`) → JSON Schema が自動生成される
- `required` / optional（デフォルト値の有無で自動判定）
- `description`（docstring）

##### パラメータに説明を付けたい場合

```python
@tool(
    allowed_roles={"base", "smart"},
    descriptions={
        "param": "このAPIに渡すパラメータの説明",
    },
)
def my_tool(param: str) -> str:
    ...
```

##### side_effect（作用系ツール）

結果を会話に戻さず short-circuit したい場合：

```python
@tool(side_effect=True, allowed_roles={"base", "smart"})
def output_to(destination: str, content: str) -> str:
    """AI が出力先を明示的に選択します"""
    ...
```

- `side_effect=True` のツール実行後、結果は会話コンテキストに追加されない
- 全ての tool_call が side_effect の場合、LLM の follow-up 呼び出しもスキップされる

#### 互換性: `register(registry)` 関数

`discover_modules()` に自動発見させるために `register()` 関数をエクスポートする：

```python
from iris.tools.decorator import tool


@tool(allowed_roles={"base", "smart"})
def my_tool(param: str) -> str:
    ...


def register(registry):
    registry.register_decorated(my_tool)
```

複数のツールがある場合：

```python
def register(registry):
    from iris.tools.decorator import register_decorated_tools
    register_decorated_tools(__import__(__name__), registry)
```

または個別に：

```python
def register(registry):
    registry.register_decorated(my_tool)
    registry.register_decorated(my_tool2)
```

### 2. Built-in として追加する場合

`iris/tools/builtins/` 以下に `.py` ファイルを作成し、`factory.py` で明示登録する：

```python
# iris/tools/builtins/my_feature.py
from iris.tools.decorator import tool


@tool(side_effect=False)
def my_builtin(data: str) -> str:
    ...


# iris/kernel/core/factory.py — _build_capabilities() 内
from iris.tools.builtins.my_feature import my_builtin
registry.register_decorated(my_builtin)
```

### 3. Verify registry discovers it

- `capabilities/<name>/server.py` → 自動発見 (`discover_modules()`)
- `iris/tools/builtins/*.py` → 手動登録 (`factory.py`)

テスト：
```python
# tests/tools/test_my_tool.py または既存の test に追加
from iris.tools.decorator import get_tool_def
from iris.capabilities.my_feature.server import my_tool

td = get_tool_def(my_tool)
assert td is not None
assert td.name == "my_tool"
assert not td.side_effect
```

### 4. Update `.iris/data/iris_profile.md`

`## My Capabilities` セクションに追加する：
```markdown
- <tool_name> — <機能の簡潔な説明>
```

### 5. Sandbox test で動作確認

```powershell
ruff check .
mypy .
pytest tests/ -q
```

### 6. Commit

```powershell
git add . && git commit -m "feat: <ツール名> capability を追加"
```

## 新旧対照表

| 項目 | 旧 (`register_func`) | 新 (`@tool()`) |
|------|---------------------|----------------|
| スキーマ定義 | 手書き `parameters` dict | 型ヒントから自動生成 |
| パラメータ説明 | dict 内に埋め込み | `descriptions` 引数 or docstring |
| 必須/任意 | `"required": True` | デフォルト値の有無で自動 |
| side_effect | 非対応 | `side_effect=True` |
| 戻り値 | `str` 固定 | `str`（ToolResult も可） |
| 登録方法 | `@registry.register_func(...)` | `@tool(...)` + `register_decorated()` |

## 注意点

- `__init__.py` を各パッケージに配置（必須）
- 戻り値は基本 `str`（LLM にツール結果として渡される文字列）
- `allowed_roles` のデフォルトは `{"base", "smart"}`（全ロールで利用可）
- 型ヒントに `Optional[str]` を使うと `nullable: true` が付与される
- 旧 `register_func` 方式も当面動作するが、新規追加は `@tool()` を推奨

## When to use me

- 新しい capability を追加するとき
- 既存 capability の構造を確認したいとき
- `@tool()` デコレータの書き方を確認したいとき
