from __future__ import annotations

TASK_KEYWORDS: frozenset[str] = frozenset(
    {
        "コード",
        "ファイル",
        "実装",
        "作成",
        "修正",
        "テスト",
        "実行",
        "ディレクトリ",
        "adr",
        "ルール",
        "ログ",
        "詳しく",
        "説明",
        "なぜ",
        "どうやって",
        "設計",
    }
)


def is_task_content(content: str) -> bool:
    if len(content) > 100 or content.startswith("/"):
        return True
    content_lower = content.lower()
    return any(kw in content_lower for kw in TASK_KEYWORDS)
