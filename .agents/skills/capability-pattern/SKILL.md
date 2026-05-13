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

新規 capability を Iris に追加する全手順をテンプレート化したものです。

## Steps

### 1. Create `capabilities/<name>/server.py`

以下のテンプレートに従ってファイルを作成する：

```python
from capabilities.registry import CapabilityRegistry


def register(registry: CapabilityRegistry):
    @registry.register_func(
        name="<tool_name>",
        description="<日本語の説明>",
        parameters={
            "<param>": {
                "type": "string",
                "description": "<日本語の説明>",
                "required": True,
            },
        },
    )
    def my_tool(param: str) -> str:
        # 実装
        return f"Result: {param}"
```

注意点：
- `__init__.py` を各パッケージに配置（必須）
- 戻り値は必ず `str`
- パラメータの型ヒントは `str` を推奨（LLMがJSONを正しくマッピングできるように）

### 2. Verify registry discovers it

capability の `server.py` を作成すると、起動時に `CapabilityRegistry.discover_modules()` が自動発見する。
手動での registry 登録は不要。

### 3. Update `memory/data/iris_profile.md`

`## My Capabilities` セクションに追加する：
```markdown
- <tool_name> — <機能の簡潔な説明>
```

### 4. Sandbox test で動作確認

テストには以下のいずれかを使用：
- `sandbox_test` ツール（capabilities/self_mod 内）：既存コードの構文チェック
- `run_python` ツール：実際の動作確認

### 5. Run lint/typecheck

```powershell
ruff check . && ruff format --check . && mypy .
```

### 6. Commit

```powershell
git add . && git commit -m "feat: <日本語で説明>"
```

## When to use me

- 新しい capability を追加するとき
- 既存 capability の構造を確認したいとき
- Capability Registry のパターンに従いたいとき
