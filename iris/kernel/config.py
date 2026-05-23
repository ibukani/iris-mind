"""
Iris v0.3 設定

Pydantic モデルで config.yaml をバリデーションする。
"""

from __future__ import annotations

import os
from pathlib import Path
import re

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
import yaml

_ENV_REF_RE = re.compile(r"\$\{([^}]+)\}")
_VALID_PERFORMANCE_TIERS = {"fast", "balanced", "capable"}


class ProviderConnection(BaseModel):
    base_url: str = ""
    api_key: str = ""


def _default_models() -> list[ModelEntry]:
    return [ModelEntry(name="qwen3.5:9b", roles=["default"], max_tokens=1024, provider="ollama")]


def _default_trigger_weights() -> dict[str, float]:
    return {
        "time": 0.25,
        "memory": 0.45,
        "context": 0.15,
        "mood": 0.15,
    }


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


class ModelEntry(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=lambda: ["default"])
    provider: str = "ollama"
    max_tokens: int = 512
    temperature: float | None = None
    num_ctx: int | None = None
    num_gpu: int | None = None
    main_gpu: int | None = None
    context_window: int | None = None
    capabilities: list[str] | None = None
    performance_tier: str = "balanced"
    tokenizer_repo_id: str = ""
    tokenizer_local_path: str = ""
    keep_alive: str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    repeat_penalty: float | None = None

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_roles(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        return ["default"]

    @field_validator("performance_tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        if v not in _VALID_PERFORMANCE_TIERS:
            raise ValueError(f"performance_tier must be one of {_VALID_PERFORMANCE_TIERS}, got '{v}'")
        return v


class ModelConfig(BaseModel):
    providers: dict[str, ProviderConnection] = Field(default_factory=dict)
    hf_token: str = ""
    models: list[ModelEntry] = Field(default_factory=_default_models)
    default_temperature: float = 0.7
    default_num_ctx: int = 8192
    default_num_gpu: int = 99
    default_context_window: int = 8192

    @property
    def model_names(self) -> list[str]:
        return [m.name for m in self.models]

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._init_role_map()

    def _init_role_map(self) -> None:
        self._role_map: dict[str, ModelEntry] = {}
        for m in self.models:
            for role in m.roles:
                self._role_map[role] = m
        self._default_entry = self.models[0] if self.models else None

    def get_model(self, role: str = "default") -> str:
        m = self._role_map.get(role, self._default_entry)
        return m.name if m else ""

    def _find_model(self, role: str) -> ModelEntry | None:
        return self._role_map.get(role, self._default_entry)

    def get_effective_temperature(self, role: str = "default") -> float:
        m = self._find_model(role)
        if m is not None and m.temperature is not None:
            return m.temperature
        return self.default_temperature

    def get_effective_num_ctx(self, role: str = "default") -> int:
        m = self._find_model(role)
        if m is not None and m.num_ctx is not None:
            return m.num_ctx
        return self.default_num_ctx

    def get_effective_num_gpu(self, role: str = "default") -> int:
        m = self._find_model(role)
        if m is not None and m.num_gpu is not None:
            return m.num_gpu
        return self.default_num_gpu

    def get_effective_context_window(self, role: str = "default") -> int:
        m = self._find_model(role)
        if m is not None and m.context_window is not None:
            return m.context_window
        return self.default_context_window

    def get_model_capabilities(self, role: str = "default") -> list[str]:
        m = self._find_model(role)
        if m is not None and m.capabilities is not None:
            return m.capabilities
        return []

    def get_model_performance_tier(self, role: str = "default") -> str:
        m = self._find_model(role)
        if m is not None:
            return m.performance_tier
        return "balanced"

    def get_effective_max_tokens(self, role: str = "default") -> int:
        m = self._find_model(role)
        if m is not None:
            return m.max_tokens
        return 4096


class ProactiveConfig(BaseModel):
    """自律的会話（自発発話）機能の設定。"""

    check_interval_sec: float = 5.0
    min_interval_sec: float = 30.0
    max_interval_sec: float = 300.0
    trigger_weights: dict[str, float] = Field(default_factory=_default_trigger_weights)
    speak_threshold: float = 0.60
    abbreviated_threshold: float = 0.25
    idle_reflection_timeout_sec: float = 180.0


class PersonalityConfig(BaseModel):
    name: str = "Iris"
    prompt_file: str = ".iris/config/personality_default.md"


class MemoryConfig(BaseModel):
    episodic_path: str = ".iris/data/episodes.jsonl"
    semantic_path: str = ".iris/data/semantic.jsonl"
    vector_db_path: str = ".iris/data/chroma_db"
    episodic_max_entries: int = 30
    semantic_max_entries: int = 100
    agents_md_path: str = ".iris/config/iris_profile.md"
    agents_md_max_bytes: int = 2048
    persona_data_path: str = ".iris/data/persona_data.json"
    persona_data_max_entries: int = 100
    psychometric_state_path: str = ".iris/data/psychometric_state.json"


class ResponseReadinessConfig(BaseModel):
    tier1_min_fragments: int = 2
    tier1_question_detect: bool = True
    confidence_threshold: float = 0.6
    llm_model_role: str = "fast"


class QuasiSyncConfig(BaseModel):
    response_readiness: ResponseReadinessConfig = Field(default_factory=ResponseReadinessConfig)


class SessionConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9876
    access_token: str = ""


class LoggingConfig(BaseModel):
    file_level: str = "INFO"
    console_level: str = ""
    dir: str = "logs"
    max_bytes: int = 5_242_880
    backup_count: int = 14
    loggers: dict[str, str] = Field(default_factory=dict)
    console_format: str = ""


class DebugConfig(BaseModel):
    enabled: bool = False
    trace_max_entries: int = 500
    emotion_history_enabled: bool = True
    personality_history_enabled: bool = True
    capture_enabled: bool = False
    capture_auto_dump: bool = False
    capture_max_entries: int = 10


class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    quasi_sync: QuasiSyncConfig = Field(default_factory=QuasiSyncConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)

    @classmethod
    def load(cls, path: str = "config.yaml") -> Config:
        load_dotenv()
        p = Path(path)
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            raw = _resolve_env_refs(raw)
            return cls.model_validate(raw)  # type: ignore[no-any-return]
        return cls()

    def save(self, path: str) -> None:
        p = Path(path)
        p.write_text(
            yaml.dump(self.model_dump(mode="python"), default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
