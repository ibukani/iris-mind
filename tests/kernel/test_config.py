from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

import pytest
import yaml

from iris.kernel.config import Config, ModelConfig, ModelEntry, ProactiveConfig


def _me(**kwargs: Any) -> ModelEntry:
    return ModelEntry(**kwargs)


def write_config_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_config_load_from_yaml() -> None:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(
            {
                "model": {
                    "models": [{"name": "qwen3.5:9b", "roles": ["default"]}],
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
                models=[{"name": "m1", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
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
            models=[{"name": "only-model", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_model("default") == "only-model"
    assert config.model.get_model("smart") == "only-model"


def test_get_model_multi_mode() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base-model", "roles": ["default"]},
                {"name": "smart-model", "roles": ["smart"]},
            ],
        ),
    )
    assert config.model.get_model("default") == "base-model"
    assert config.model.get_model("smart") == "smart-model"


def test_get_model_unknown_role_falls_back() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "only-model", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_model("unknown_role") == "only-model"


def test_get_model_multi_unknown_falls_back() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base", "roles": ["default"]},
                {"name": "smart", "roles": ["smart"]},
            ],
        ),
    )
    assert config.model.get_model("nonexistent") == "base"


def test_env_var_resolution() -> None:
    os.environ["TEST_IRIS_API_KEY"] = "my-test-key-123"
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(
            {
                "model": {
                    "providers": {
                        "openrouter": {
                            "api_key": "${TEST_IRIS_API_KEY}",
                            "base_url": "http://localhost:11434",
                        },
                    },
                    "models": [
                        {
                            "name": "m",
                            "roles": ["default"],
                            "provider": "openrouter",
                        },
                    ],
                },
            },
            f,
        )
        path = f.name

    try:
        config = Config.load(path)
        assert config.model.providers["openrouter"].api_key == "my-test-key-123"
    finally:
        os.unlink(path)
        del os.environ["TEST_IRIS_API_KEY"]


def test_default_values() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "m", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.default_temperature == 0.7
    assert config.model.default_num_gpu == 99
    assert config.model.default_num_ctx == 8192
    assert config.model.default_context_window == 8192
    assert config.model.models[0].provider == "ollama"
    assert config.model.models[0].name == "m"
    assert config.model.providers == {}
    assert config.model.hf_token == ""
    assert config.personality.name == "Iris"


def test_proactive_config_defaults() -> None:
    config = ProactiveConfig()
    assert config.check_interval_sec == 5.0
    assert config.min_interval_sec == 30.0
    assert config.speak_threshold == 0.6
    assert config.trigger_weights["memory"] == 0.55
    assert config.trigger_weights["context"] == 0.30


def test_config_mutable_defaults_are_independent() -> None:
    first = Config()
    second = Config()

    first.proactive.trigger_weights["memory"] = 0.99
    first.logging.loggers["iris"] = "DEBUG"

    assert second.proactive.trigger_weights["memory"] == 0.55
    assert second.logging.loggers == {}


# ── Step 1: Per-model parameters ──────────────────────────────


def test_model_entry_defaults() -> None:
    entry = ModelEntry(name="test")
    assert entry.max_tokens == 512
    assert entry.temperature is None
    assert entry.num_ctx is None
    assert entry.capabilities is None
    assert entry.performance_tier == "balanced"


def test_model_entry_valid_performance_tiers() -> None:
    for tier in ("fast", "balanced", "capable"):
        entry = ModelEntry(name="test", performance_tier=tier)
        assert entry.performance_tier == tier


def test_model_entry_invalid_performance_tier() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModelEntry(name="test", performance_tier="invalid")


def test_get_effective_temperature_per_model() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base", "roles": ["default"], "temperature": 0.5},
                {"name": "smart", "roles": ["smart"], "temperature": 0.9},
            ],
        ),
    )
    assert config.model.get_effective_temperature("default") == 0.5
    assert config.model.get_effective_temperature("smart") == 0.9


def test_get_effective_temperature_fallback() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "base", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_effective_temperature("default") == 0.7


def test_get_effective_temperature_unknown_role() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "base", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_effective_temperature("nonexistent") == 0.7


def test_get_effective_num_ctx() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base", "roles": ["default"], "num_ctx": 4096},
            ],
        ),
    )
    assert config.model.get_effective_num_ctx("default") == 4096
    # unknown role falls back to models[0] which has num_ctx=4096
    assert config.model.get_effective_num_ctx("unknown") == 4096


def test_get_model_capabilities_explicit() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base", "roles": ["default"], "capabilities": ["tools"]},
                {"name": "smart", "roles": ["smart"], "capabilities": ["tools", "thinking"]},
            ],
        ),
    )
    assert config.model.get_model_capabilities("default") == ["tools"]
    assert config.model.get_model_capabilities("smart") == ["tools", "thinking"]


def test_get_model_capabilities_none() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "base", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_model_capabilities("default") == []


def test_get_model_performance_tier() -> None:
    config = Config(
        model=ModelConfig(
            models=[  # pyright: ignore[reportArgumentType]
                {"name": "base", "roles": ["default"], "performance_tier": "capable"},
                {"name": "fast", "roles": ["fast"], "performance_tier": "fast"},
            ],
        ),
    )
    assert config.model.get_model_performance_tier("default") == "capable"
    assert config.model.get_model_performance_tier("fast") == "fast"


def test_get_model_performance_tier_default() -> None:
    config = Config(
        model=ModelConfig(
            models=[{"name": "base", "roles": ["default"]}],  # pyright: ignore[reportArgumentType]
        ),
    )
    assert config.model.get_model_performance_tier("default") == "balanced"
