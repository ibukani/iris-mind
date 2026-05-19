from __future__ import annotations

import logging
import os
from pathlib import Path

from tokenizers import Tokenizer

logger = logging.getLogger(__name__)


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
        if local_path:
            p = Path(local_path)
            if p.exists():
                try:
                    self._tokenizer = Tokenizer.from_file(str(p))
                    logger.info("Tokenizer loaded from local: %s", local_path)
                    return
                except Exception as e:
                    logger.warning("Failed to load tokenizer from %s: %s", local_path, e)
            else:
                logger.warning("Tokenizer local_path not found: %s", local_path)

        if repo_id:
            if hf_token:
                os.environ.setdefault("HF_TOKEN", hf_token)
            try:
                self._tokenizer = Tokenizer.from_pretrained(repo_id)
                logger.info("Tokenizer loaded from HF Hub: %s (vocab=%d)", repo_id, self._tokenizer.get_vocab_size())
            except Exception as e:
                logger.warning("Failed to load tokenizer from %s: %s", repo_id, e)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text))
        return max(1, len(text) // 2)

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        return sum(self.estimate_tokens(m.get("content", "")) for m in messages)

    @property
    def is_available(self) -> bool:
        return self._tokenizer is not None
