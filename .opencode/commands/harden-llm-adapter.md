---
description: LLM adapter 周りの堅牢性を調査・改善する。
---

@planner

対象: `iris/llm`, `iris/agency/execution/llm`, `iris/agency/execution/nodes`

まずコード変更せず、LLM adapter 周りの堅牢性を調査してください。

## 初期調査対象

```text
iris/llm/
iris/kernel/config.py
iris/agency/execution/llm/
iris/agency/execution/nodes/
tests/
```

## 観点

- model/provider routing
- cache key safety
- environment variable validation
- capability-driven tools/thinking
- `temperature=0.0`
- streaming cancellation
- tests avoiding real external LLM calls

## 出力

- 問題一覧
- 変更候補
- テスト方針
- リスク
- 実装順序

実装は、計画確認後に `/implement-feature` または `/fix-bug` で行ってください。
