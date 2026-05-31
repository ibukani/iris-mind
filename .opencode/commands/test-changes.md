---
description: 現在の差分に対してテスト追加・検証・失敗原因切り分けを行う。
---

@tester

現在の差分を確認し、必要なテストを追加・更新してください。

## 実行してほしいこと

1. 差分確認
2. 関連テストの確認
3. 不足テストの追加
4. 可能な範囲で検証実行
5. 失敗が残る場合は原因を切り分ける

## 検証候補

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

依存不足で止まる場合は、不足内容を明記してください。
