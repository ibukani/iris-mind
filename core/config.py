from pathlib import Path
import yaml
from pydantic import BaseModel


class ModelConfig(BaseModel):
    name: str = "qwen3.5:9b"
    base_url: str = "http://localhost:11434"
    max_tokens: int = 4096
    temperature: float = 0.7


class PersonalityConfig(BaseModel):
    name: str = "Iris"
    description_file: str = "memory/iris_profile.md"
    thinking_mode_default: bool = False


class MemoryConfig(BaseModel):
    vector_db_path: str = "memory/chroma_db"
    episodic_max_entries: int = 30
    semantic_max_entries: int = 100
    rag_max_results: int = 3
    agents_md_path: str = "memory/iris_profile.md"
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
