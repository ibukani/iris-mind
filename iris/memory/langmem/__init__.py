"""LangMem ベースの記憶抽出パイプライン。

Memory plugin のサブモジュール。LangMem は候補抽出エンジンとしてのみ用い、
最終的な記憶の確定・保存・関係性更新は Iris 側 (PromotionPolicy / 各ストア) で行う。

サブモジュール:
- ``extractor``: ローカル ChatModel から ``MemoryCandidate`` を抽出
- ``stores``: 候補 / ジョブの JSONL ストア (重複検出付き)
- ``dedup``: 候補のハッシュ計算ヘルパ
- ``promotion``: 候補の昇格ルールと Handler ディスパッチ
- ``handlers``: target_store ごとの保守的昇格ロジック
- ``scheduler``: ``MemoryPipeline`` をバックグラウンド化するスケジューラ
- ``pipeline``: 上記コンポーネントを統合したパイプライン
"""
