---
description: 指定された機能・変更を実装する。
---

@implementer

実装内容: `$1`

指定された機能または変更を実装してください。

## ルール

- 事前に必要な範囲を調査する
- 変更範囲を必要最小限にする
- 変更した挙動にはテストを追加・更新する
- provider 固有処理を上位レイヤーに漏らさない
- memory / limbic / execution / transport の責務境界を崩さない

## 検証候補

```bash
uv run pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```
