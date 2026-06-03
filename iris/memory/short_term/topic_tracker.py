from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.memory.short_term.store import ShortTermStore


class TopicTracker:
    """topicの抽出・更新。"""

    def __init__(self, store: ShortTermStore) -> None:
        self._store = store

    def extract_topics(self, content: str) -> None:
        sentences = re.split(r"[。！？\.\!\?]", content)
        for s in sentences[:2]:
            s = s.strip()
            if len(s) > 5 and len(s) < 80 and s not in self._store.current_topics:
                self._store.add_topic(s)
