"""Raw Conversation Archive — 会話ログの append-only 永続化。

Memory plugin のサブモジュール。短期記憶・意味記憶・エピソード記憶とは独立した
「生の対話アーカイブ」を JSONL で保存し、LangMem 抽出や障害解析の入力として再利用する。
"""
