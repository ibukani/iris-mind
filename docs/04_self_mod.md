# 自己改変モジュール

## 基本方針

LLMの重みは変更せず、「AIが利用できる環境」を変更することで自己拡張を実現する。

- **重みは不変**、コードと設定のみ変更対象
- **ユーザー承認が必須**（AI単独では変更不可）
- **テスト通過が必須**（変更後、既存機能を壊していないか確認）

## Capability テンプレート

```python
# capabilities/example/server.py
from core.registry import capability

@capability(
    name="example_tool",
    description="〇〇を行うツール",
    parameters={
        "param1": {"type": "string", "description": "パラメータ1"}
    }
)
def example_tool(param1: str) -> str:
    """実際の処理"""
    return result
```

## 自己改変フロー

```
1. AIが「このcapabilityが不足している」と判断
   （会話中またはReflexionで検出）

2. AIがコードを生成
   → capabilities/new_tool/server.py を作成

3. ユーザーに差分表示
   "以下の機能を追加します。承認しますか？"
   ┌─────────────────────────────────┐
   │ + new_tool/server.py (123行)    │
   │ + new_tool/tool_schema.json     │
   │ - old_tool/server.py (修正)      │
   └─────────────────────────────────┘

4. ユーザー承認後、サンドボックスでテスト
   - 構文チェック（py_compile）
   - スキーマ検証
   - モック実行

5. テストOK → Capability Registry に登録
           → AGENTS.md に記録
   テストNG → 修正コードを再生成 → ユーザーに再提示
```

## 安全性

- 変更前のファイルは自動でgit管理（あれば）またはバックアップ
- サンドボックスは隔離されたPythonサブプロセスで実行
- すべての変更にユーザー承認が必要
