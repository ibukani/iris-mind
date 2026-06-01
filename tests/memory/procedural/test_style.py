"""StyleMemoryStore / renderer / prompt 統合のテスト。"""

from __future__ import annotations

from pathlib import Path

from iris.llm.prompt import Personality
from iris.memory.procedural.models import StyleMemory
from iris.memory.procedural.renderer import build_style_hints, render_style_hints
from iris.memory.procedural.style_store import StyleMemoryStore


def test_style_memory_store_roundtrip(tmp_path: Path) -> None:
    store = StyleMemoryStore(str(tmp_path / "s.jsonl"))
    m = StyleMemory(kind="tone_preference", content="カジュアルに", confidence=0.8)
    store.add(m)
    items = store.list_all()
    assert len(items) == 1
    assert items[0].content == "カジュアルに"


def test_list_enabled_filters_by_scope(tmp_path: Path) -> None:
    store = StyleMemoryStore(str(tmp_path / "s.jsonl"))
    store.add(StyleMemory(kind="tone_preference", content="global-tone", confidence=0.9, scope="global"))
    store.add(
        StyleMemory(
            kind="tone_preference",
            content="acc1-tone",
            confidence=0.9,
            scope="account",
            account_id="acc1",
        )
    )
    store.add(
        StyleMemory(
            kind="tone_preference",
            content="acc2-tone",
            confidence=0.9,
            scope="account",
            account_id="acc2",
        )
    )
    store.add(
        StyleMemory(
            kind="tone_preference",
            content="disabled-tone",
            confidence=0.9,
            scope="global",
            enabled=False,
        )
    )

    items = store.list_enabled(account_id="acc1", max_items=10)
    contents = {i.content for i in items}
    assert "global-tone" in contents
    assert "acc1-tone" in contents
    assert "acc2-tone" not in contents
    assert "disabled-tone" not in contents


def test_render_style_hints_includes_kind_prefix() -> None:
    items = [
        StyleMemory(kind="tone_preference", content="be casual"),
        StyleMemory(kind="avoidance_rule", content="never say X"),
    ]
    text = render_style_hints(items)
    assert "[tone] be casual" in text
    assert "[avoid] never say X" in text


def test_build_style_hints_uses_store(tmp_path: Path) -> None:
    store = StyleMemoryStore(str(tmp_path / "s.jsonl"))
    store.add(StyleMemory(kind="successful_pattern", content="be specific", confidence=0.9))
    text = build_style_hints(store, max_items=2)
    assert "[pattern] be specific" in text


def test_prompt_includes_style_hints() -> None:
    personality = Personality()
    text = personality.build_system_prompt(
        agents_md_content="",
        style_hints="- [pattern] be specific",
    )
    assert "## 動的スタイル記憶" in text
    assert "[pattern] be specific" in text


def test_style_hints_absent_when_empty() -> None:
    personality = Personality()
    text = personality.build_system_prompt(agents_md_content="", style_hints="")
    assert "動的スタイル記憶" not in text
