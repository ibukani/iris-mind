"""
Iris v0.2 設定

Pydantic モデルで config.yaml をバリデーションする。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

# ── ユーティリティ ────────────────────────────────────────

_ENV_REF_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_refs(raw: object) -> object:
    """設定値中の ${VAR_NAME} を環境変数で置換する（文字列のみ対象）。"""
    if isinstance(raw, str):

        def _replace(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1), m.group(0))

        return _ENV_REF_RE.sub(_replace, raw)
    if isinstance(raw, dict):
        return {k: _resolve_env_refs(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_resolve_env_refs(v) for v in raw]
    return raw


# ── モデル定義 ────────────────────────────────────────────


class ModelEntry(BaseModel):
    name: str
    roles: list[str] = ["default"]
    max_tokens: int = 512

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_roles(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        return ["default"]


class ModelConfig(BaseModel):
    models: list[ModelEntry] = [
        ModelEntry(name="qwen3.5:9b", roles=["default"], max_tokens=1024),
    ]
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    temperature: float = 0.7
    num_gpu: int = 0
    num_ctx: int = 8192
    context_window: int = 0
    compaction_threshold: float = 0.85

    @property
    def model_names(self) -> list[str]:
        return [m.name for m in self.models]

    def get_model(self, role: str = "default") -> str:
        for m in self.models:
            if role in m.roles:
                return m.name
        return self.models[0].name


# ── 新規: ProactiveConfig ───────────────────────────────


class ProactiveConfig(BaseModel):
    """自律的会話（自発発話）機能の設定。"""

    enabled: bool = False
    check_interval_sec: float = 5.0
    min_interval_sec: float = 30.0
    max_interval_sec: float = 300.0
    tier1_auto_approve: bool = True
    tier2_confidence_threshold: float = 0.75
    tier2_cooldown_sec: float = 60.0
    max_proactive_tokens: int = 256
    user_cooldown_on_ignore: float = 300.0
    trigger_weights: dict[str, float] = {
        "time": 0.25,
        "memory": 0.45,
        "context": 0.15,
        "mood": 0.15,
    }
    speak_threshold: float = 0.60


class PersonalityConfig(BaseModel):
    name: str = "Iris"
    thinking_mode_default: bool = False
    mode_default: str = "auto"
    prompt_file: str = ".iris/config/personality_default.md"


class MemoryConfig(BaseModel):
    episodic_path: str = ".iris/data/episodes.jsonl"
    semantic_path: str = ".iris/data/semantic.jsonl"
    vector_db_path: str = ".iris/data/chroma_db"
    episodic_max_entries: int = 30
    semantic_max_entries: int = 100
    rag_max_results: int = 3
    agents_md_path: str = ".iris/data/iris_profile.md"
    agents_md_max_bytes: int = 2048


class Config(BaseModel):
    model: ModelConfig = ModelConfig()
    personality: PersonalityConfig = PersonalityConfig()
    memory: MemoryConfig = MemoryConfig()
    proactive: ProactiveConfig = ProactiveConfig()

    @classmethod
    def load(cls, path: str = "config.yaml") -> Config:
        load_dotenv()
        p = Path(path)
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            raw = _resolve_env_refs(raw)
            return cls.model_validate(raw)
        return cls()

    def save(self, path: str):
        p = Path(path)
        p.write_text(
            yaml.dump(self.model_dump(mode="python"), default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
