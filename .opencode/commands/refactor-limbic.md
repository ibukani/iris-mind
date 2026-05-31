---
description: limbic レイヤーの責務境界を整理する。まず設計計画だけを作る。
---

@architect

対象: `iris/limbic`

まずコード変更せず、以下の観点で設計計画を作ってください。

## 目的

AI コンパニオンとして拡張しやすいように、appraisal / mood / relationship / emotion state の責務を明確にする。

## 見るファイル

```text
iris/limbic/appraiser.py
iris/limbic/orchestrator.py
iris/limbic/classifier.py
iris/limbic/relationship.py
iris/limbic/mood.py
iris/limbic/state.py
```

## 計画に含めること

- appraisal をイベント単位に分離する案
- mood を持続状態として扱う案
- emotion_state を短期状態として扱う案
- relationship を person-specific に整理する案
- orchestrator を薄くする案
- memory との境界
- agency/execution との境界
- 追加・更新すべきテスト
- 避けるべき過剰抽象化

## 注意

- limbic から LLM provider を直接呼ばない
- memory persistence を limbic に移さない
- response generation を limbic に入れない
- 実装はまだ行わないでください。計画が合意されたら `/implement-plan` を使います。
