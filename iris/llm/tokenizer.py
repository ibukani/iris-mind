from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tokenizers import Tokenizer

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
        self._token_cache: dict[str, int] = {}
        self._token_cache_maxsize = 2048
        self._load(repo_id, local_path, hf_token)

    def _load(self, repo_id: str, local_path: str, hf_token: str) -> None:
        if local_path:
            self._load_local(local_path)
        if self._tokenizer is None and repo_id:
            self._load_hub(repo_id, hf_token)

    def _load_local(self, local_path: str) -> None:
        from tokenizers import Tokenizer

        p = Path(local_path)
        if not p.exists():
            logger.warning("Tokenizer local_path not found: {}", local_path)
            return
        try:
            self._tokenizer = Tokenizer.from_file(str(p))
            logger.info("Tokenizer loaded from local: {}", local_path)
        except Exception as e:
            logger.warning("Failed to load tokenizer from {}: {}", local_path, e)

    def _load_hub(self, repo_id: str, hf_token: str) -> None:
        from tokenizers import Tokenizer

        if hf_token:
            os.environ.setdefault("HF_TOKEN", hf_token)
        try:
            t = Tokenizer.from_pretrained(repo_id)
            if t is not None:
                self._tokenizer = t
                logger.info("Tokenizer loaded from HF Hub: {} (vocab={})", repo_id, t.get_vocab_size())
        except Exception as e:
            logger.warning("Failed to load tokenizer from {}: {}", repo_id, e)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        if text in self._token_cache:
            return self._token_cache[text]
        result = len(self._tokenizer.encode(text)) if self._tokenizer is not None else int(len(text) * 1.3)
        if len(self._token_cache) >= self._token_cache_maxsize:
            self._token_cache.clear()
        self._token_cache[text] = result
        return result

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        return sum(self.estimate_tokens(m.get("content", "")) for m in messages)

    @property
    def is_available(self) -> bool:
        return self._tokenizer is not None
