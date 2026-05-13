from pathlib import Path
import yaml
from pydantic import BaseModel


class ModelConfig(BaseModel):
    smart_model: str = "qwen3.5:9b"
    fast_model: str | None = None
    base_url: str = "http://localhost:11434"
    max_tokens: int = 1024
    max_tokens_fast: int = 256
    temperature: float = 0.7
    draft_model: str | None = None
    num_draft: int = 5
    num_gpu: int = 0
    num_ctx: int = 8192
    context_window: int = 0
    compaction_threshold: float = 0.85


class PersonalityConfig(BaseModel):
    name: str = "Iris"
    thinking_mode_default: bool = False
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

    @property
    def model_names(self) -> list[str]:
        names = [self.model.smart_model]
        if self.model.fast_model:
            names.append(self.model.fast_model)
        if self.model.draft_model:
            names.append(self.model.draft_model)
        return names

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
