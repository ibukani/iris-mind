from __future__ import annotations

import os
from pathlib import Path
import re

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import yaml

from iris.kernel.config.models import (
    _ENV_REF_RE,
    DebugConfig,
    InhibitionConfig,
    LimbicConfig,
    LoggingConfig,
    MemoryConfig,
    ModelConfig,
    PersonalityConfig,
    PluginConfig,
    ProactiveConfig,
    QuasiSyncConfig,
    SessionConfig,
    TimerConfig,
)


def _resolve_env_refs(raw: object) -> object:
    if isinstance(raw, str):

        def _replace(m: re.Match[str]) -> str:
            name = m.group(1)
            value = os.environ.get(name)
            if value is None:
                raise ValueError(f"Environment variable {name} is not set")
            return value

        return _ENV_REF_RE.sub(_replace, raw)
    if isinstance(raw, dict):
        return {k: _resolve_env_refs(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_resolve_env_refs(v) for v in raw]
    return raw


class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    limbic: LimbicConfig = Field(default_factory=LimbicConfig)
    inhibition: InhibitionConfig = Field(default_factory=InhibitionConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    timer: TimerConfig = Field(default_factory=TimerConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    quasi_sync: QuasiSyncConfig = Field(default_factory=QuasiSyncConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    plugins: PluginConfig = Field(default_factory=PluginConfig)

    @classmethod
    def load(cls, path: str = "config.yaml") -> Config:
        load_dotenv()
        p = Path(path)
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            raw = _resolve_env_refs(raw)
            return cls.model_validate(raw)
        return cls()

    def save(self, path: str) -> None:
        p = Path(path)
        p.write_text(
            yaml.dump(self.model_dump(mode="python"), default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
