from __future__ import annotations

import re
from typing import Protocol


class EntityExtractor(Protocol):
    def extract(self, content: str) -> list[str]: ...


class RegexEntityExtractor:
    def extract(self, content: str) -> list[str]:
        entities: list[str] = []
        entities.extend(re.findall(r"https?://[^\s]+", content))
        entities.extend(re.findall(r"(?:/[^\s/]+)+(?:/?)", content))
        entities.extend(re.findall(r"#\w+", content))
        entities.extend(re.findall(r"@\w+", content))
        entities.extend(re.findall(r"「([^」]+)」", content))
        entities.extend(re.findall(r'"([^"]{3,})"', content))
        entities.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", content))
        return list({e for e in entities if len(e) > 2})
