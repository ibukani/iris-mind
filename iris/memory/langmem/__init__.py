"""LangMem ベースの記憶抽出パイプライン。

Memory plugin のサブモジュール。LangMem は候補抽出エンジンとしてのみ用い、
最終的な記憶の確定・保存・関係性更新は Iris 側 (PromotionPolicy / 各ストア) で行う。
"""
