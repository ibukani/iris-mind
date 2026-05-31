---
description: memory レイヤーの責務整理を段階的に行う。まず計画だけを作る。
---

@planner

対象: `iris/memory`

まずコード変更せず、以下の観点で計画を作ってください。

## 目的

短期記憶・長期記憶・感覚記憶の責務を整理し、manager を orchestration に寄せる。

## 見るファイル

```text
iris/memory/manager.py
iris/memory/short_term/manager.py
iris/memory/short_term/extractor.py
iris/memory/short_term/scorer.py
iris/memory/short_term/renderer.py
iris/memory/sensory/manager.py
iris/memory/long_term/manager.py
```

## 計画に含めること

- short_term manager から切り出すべき責務
- long_term manager から切り出すべき責務
- sensory manager から切り出すべき責務
- retention / consolidation / retrieval / rendering の配置
- persistence 形式への影響
- memory と limbic の境界
- 追加・更新すべきテスト
- 触らない方がよいファイル

## 注意

- memory から limbic の内部状態を直接更新しない
- prompt rendering と保存処理を混ぜない
- 実装はまだ行わないでください。計画が合意されたら `/implement-plan` を使います。
