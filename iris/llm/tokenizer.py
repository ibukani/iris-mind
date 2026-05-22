from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tokenizers import Tokenizer

from cachetools import LRUCache, cached
from loguru import logger


class TokenizerManager:
    """モデル名→トークナイザーの解決とトークン推定を行う。

    解決順:
      1. local_path → tokenizer.json をローカルから直接読み込み
      2. repo_id → HuggingFace Hub から from_pretrained (HF_TOKEN 対応)
      3. Fallback → len//2 推定
    """

    def __init__(
        self,
        repo_id: str = "",
        local_path: str = "",
        hf_token: str = "",
    ) -> None:
        self._tokenizer: Tokenizer | None = None
        self._load(repo_id, local_path, hf_token)

    def _load(self, repo_id: str, local_path: str, hf_token: str) -> None:
        from tokenizers import Tokenizer

        loaded = False
        if local_path:
            p = Path(local_path)
            if p.exists():
                try:
                    self._tokenizer = Tokenizer.from_file(str(p))
                    logger.info("Tokenizer loaded from local: %s", local_path)
                    loaded = True
                except Exception as e:
                    logger.warning("Failed to load tokenizer from %s: %s", local_path, e)
            else:
                logger.warning("Tokenizer local_path not found: %s", local_path)

        if not loaded and repo_id:
            if hf_token:
                os.environ.setdefault("HF_TOKEN", hf_token)
            try:
                t = Tokenizer.from_pretrained(repo_id)
                if t is not None:
                    self._tokenizer = t
                    logger.info("Tokenizer loaded from HF Hub: %s (vocab=%d)", repo_id, t.get_vocab_size())
            except Exception as e:
                logger.warning("Failed to load tokenizer from %s: %s", repo_id, e)

    @cached(cache=LRUCache(maxsize=2048))
    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text))
        # 日本語等のマルチバイトを考慮し、安全側に倒す (1文字あたり約1.3トークン)
        return int(len(text) * 1.3)

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        return sum(self.estimate_tokens(m.get("content", "")) for m in messages)

    @property
    def is_available(self) -> bool:
        return self._tokenizer is not None
