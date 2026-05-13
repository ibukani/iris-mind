from pathlib import Path

import yaml
from pydantic import BaseModel


class ModelEntry(BaseModel):
    name: str
    role: str = "base"
    max_tokens: int = 512


class EscalationConfig(BaseModel):
    enabled: bool = True
    max_retries: int = 1
    swap_on_escalate: bool = True
    keep_alive_duration: str = "5m"


class ModelConfig(BaseModel):
    models: list[ModelEntry] = [
        ModelEntry(name="qwen3.5:2b", role="base", max_tokens=512),
        ModelEntry(name="qwen3.5:9b", role="smart", max_tokens=1024),
    ]
    escalation: EscalationConfig = EscalationConfig()
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    num_gpu: int = 0
    num_ctx: int = 8192
    context_window: int = 0
    compaction_threshold: float = 0.85

    @property
    def model_names(self) -> list[str]:
        return [m.name for m in self.models]

    @property
    def base_model(self) -> str:
        return next((m.name for m in self.models if m.role == "base"), self.models[0].name)

    @property
    def smart_model(self) -> str:
        return next((m.name for m in self.models if m.role == "smart"), self.models[-1].name)


class PersonalityConfig(BaseModel):
    name: str = "Iris"
    mode_default: str = "auto"
    prompt_file: str = "memory/personality_default.md"


class MemoryConfig(BaseModel):
    episodic_path: str = "memory/data/episodes.jsonl"
    semantic_path: str = "memory/data/semantic.jsonl"
    vector_db_path: str = "memory/data/chroma_db"
    episodic_max_entries: int = 30
    semantic_max_entries: int = 100
    rag_max_results: int = 3
    agents_md_path: str = "memory/data/iris_profile.md"
    agents_md_max_bytes: int = 2048


class Config(BaseModel):
    model: ModelConfig = ModelConfig()
    personality: PersonalityConfig = PersonalityConfig()
    memory: MemoryConfig = MemoryConfig()

    @classmethod
    def load(cls, path: str = "config.yaml") -> "Config":
        p = Path(path)
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            return cls.model_validate(raw)
        return cls()

    def save(self, path: str):
        p = Path(path)
        p.write_text(
            yaml.dump(self.model_dump(mode="python"), default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
