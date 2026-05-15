---
name: capability-pattern
description: Iris capability 追加の最小ワークフロー
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

新規 capability（ツール）を Iris に追加するときだけ読む。
詳細調査は既存 capability と `iris/tools/` の実装を一次情報にする。

## Steps

1. 配置を決める

- 通常: `iris/capabilities/<name>/server.py`
- built-in: `iris/tools/builtins/` に実装し、`iris/kernel/core/factory.py` で明示登録

2. `@tool()` で定義する

```python
from iris.tools.decorator import tool


@tool(allowed_roles={"base", "smart"})
def my_tool(param: str) -> str:
    """日本語の説明。この docstring が tool description になる。"""
    return f"Result: {param}"
```

- 型ヒントから JSON Schema が生成される
- デフォルト値なしは required、ありは optional
- パラメータ説明が必要な場合は `descriptions={...}` を使う
- 会話に結果を戻さない作用系ツールは `side_effect=True` を使う

3. 自動発見用 `register()` を置く

```python
def register(registry):
    registry.register_decorated(my_tool)
```

複数ツールの場合は `iris.tools.decorator.register_decorated_tools` の既存利用例を参照する。

4. テストを追加する

- `tests/tools/` または関連領域の既存テストに追加
- 最低限、`get_tool_def()` で name / schema / `side_effect` / `allowed_roles` を確認する
- 実行時の副作用がある場合は Fake や一時ディレクトリで検証する

5. ドキュメントと構造記憶を更新する

- `.iris/data/iris_profile.md` の `## My Capabilities`
- 必要なら `docs/` または `docs/adr/`
- ドキュメント更新漏れ確認は `.agents/skills/doc-sync/SKILL.md`

6. 検証してコミットする

```powershell
ruff check .
mypy .
pytest tests/ -q
git add .
git commit -m "feat: <ツール名> capability を追加"
```

## Rules

- 新規追加は `@tool()` を使う。旧 `register_func()` は既存互換用。
- `__init__.py` を必要なパッケージに置く。
- 戻り値は基本 `str`。
- `allowed_roles` を指定しない場合は全ロール利用可。
