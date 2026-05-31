---
description: agency/execution レイヤーの責務整理を段階的に行う。まず計画だけを作る。
---

@planner

対象: `iris/agency/execution`

まずコード変更せず、以下の観点で計画を作ってください。

## 目的

`agency/execution` を LLM adapter / provider / capability 設計と整合させる。

## 見るファイル

```text
iris/agency/execution/llm/gateway.py
iris/agency/execution/llm/prompt_builder.py
iris/agency/execution/llm/profile_builder.py
iris/agency/execution/llm/node_prompt_factory.py
iris/agency/execution/nodes/base.py
iris/agency/execution/nodes/general_chat.py
iris/agency/execution/nodes/general_task.py
iris/agency/execution/nodes/tool_run.py
iris/agency/execution/orchestrator.py
iris/agency/execution/router.py
iris/agency/execution/executor.py
iris/llm/bridge.py
iris/llm/capabilities.py
```

## 計画に含めること

- `LLMGateway` から切り出すべき責務
- `ModelInvocationPolicy` を追加すべきか
- `NodeToolPolicy` を追加すべきか
- tool / routing tools / thinking / temperature の判断場所
- capability checker の扱い
- 追加・更新すべきテスト
- 触らない方がよいファイル

## 注意

実装はまだ行わないでください。計画が合意されたら `/implement-plan` を使います。
