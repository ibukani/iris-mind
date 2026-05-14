from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from iris.kernel.config import Config, ModelConfig, ProactiveConfig


def write_config_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_config_load_from_yaml() -> None:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(
            {
                "model": {
                    "models": [{"name": "qwen3.5:9b", "roles": ["default"]}],
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                },
                "personality": {"name": "Iris"},
                "memory": {
                    "episodic_path": ".iris/data/episodes.jsonl",
                    "semantic_path": ".iris/data/semantic.jsonl",
                },
            },
            f,
        )
        path = f.name

    try:
        config = Config.load(path)
        assert config.model.get_model("default") == "qwen3.5:9b"
        assert config.personality.name == "Iris"
    finally:
        os.unlink(path)


def test_config_save_and_reload() -> None:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        path = f.name

    try:
        config = Config(
            model=ModelConfig(
                models=[{"name": "m1", "roles": ["default"]}],
                provider="ollama",
                base_url="http://localhost:11434",
            ),
        )
        config.save(path)
        loaded = Config.load(path)
        assert loaded.model.get_model("default") == "m1"
    finally:
        os.unlink(path)


def test_get_model_single_mode() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "only-model", "roles": ["default"]}],
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )
    assert config.model.get_model("default") == "only-model"
    assert config.model.get_model("smart") == "only-model"


def test_get_model_multi_mode() -> None:
    config = Config(
        model=ModelConfig(
            models=[
                {"name": "base-model", "roles": ["default"]},
                {"name": "smart-model", "roles": ["smart"]},
            ],
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )
    assert config.model.get_model("default") == "base-model"
    assert config.model.get_model("smart") == "smart-model"


def test_get_model_unknown_role_falls_back() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "only-model", "roles": ["default"]}],
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )
    assert config.model.get_model("unknown_role") == "only-model"


def test_get_model_multi_unknown_falls_back() -> None:
    config = Config(
        model=ModelConfig(
            models=[
                {"name": "base", "roles": ["default"]},
                {"name": "smart", "roles": ["smart"]},
            ],
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )
    assert config.model.get_model("nonexistent") == "base"


def test_env_var_resolution() -> None:
    os.environ["TEST_IRIS_API_KEY"] = "my-test-key-123"
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(
            {
                "model": {
                    "models": [{"name": "m", "roles": ["default"]}],
                    "provider": "openrouter",
                    "api_key": "${TEST_IRIS_API_KEY}",
                    "base_url": "http://localhost:11434",
                },
            },
            f,
        )
        path = f.name

    try:
        config = Config.load(path)
        assert config.model.api_key == "my-test-key-123"
    finally:
        os.unlink(path)
        del os.environ["TEST_IRIS_API_KEY"]


def test_default_values() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "m", "roles": ["default"]}],
            provider="ollama",
            base_url="http://localhost:11434",
        ),
    )
    assert config.model.temperature == 0.7
    assert config.model.num_gpu == 0
    assert config.model.num_ctx == 8192
    assert config.model.context_window == 0
    assert config.model.compaction_threshold == 0.85
    assert config.personality.name == "Iris"
    assert config.personality.thinking_mode_default is False


def test_proactive_config_defaults() -> None:
    config = ProactiveConfig()
    assert config.enabled is False
    assert config.check_interval_sec == 5.0
    assert config.min_interval_sec == 30.0
    assert config.speak_threshold == 0.6
    assert config.tier1_auto_approve is True
    assert config.tier2_confidence_threshold == 0.75
    assert config.trigger_weights["time"] == 0.25
