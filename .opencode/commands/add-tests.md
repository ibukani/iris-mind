---
description: 現在の差分または指定対象にテストを追加する。
---

@tester

対象: `$1`

必要なテストを追加・更新してください。

## ルール

- 差分や指定ファイルだけを完全な対象範囲とみなさない
- 参照元、既存テスト、config、entrypoint を確認する
- 外部 LLM API や Ollama 起動に依存させない
- テストを通すために仕様を弱めない

## 検証候補

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
