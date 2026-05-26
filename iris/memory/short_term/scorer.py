from __future__ import annotations

import re
from typing import Protocol


class ImportanceScorer(Protocol):
    def score(self, content: str) -> int: ...


class DefaultImportanceScorer:
    def score(self, content: str) -> int:
        score = 0
        lower = content.lower()
        if any(w in lower for w in ["important", "大事", "覚えて", "remember", "注意", "critical", "urgent"]):
            score += 3
        if any(w in lower for w in ["please", "お願い", "help", "assist", "question", "質問"]):
            score += 1
        if re.search(r"[A-Z]{3,}", content):
            score += 1
        if content.count("!") >= 2:
            score += 1
        return min(score, 5)
