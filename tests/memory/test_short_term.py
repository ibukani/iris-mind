from __future__ import annotations

import pytest

from iris.memory.short_term.manager import ShortTermMemoryManager


@pytest.fixture()
def stm() -> ShortTermMemoryManager:
    return ShortTermMemoryManager(max_turns=10, max_topics=5)


class TestAddTurn:
    def test_add_turn_user(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "こんにちは")
        assert stm.turn_count == 1
        assert stm._turns[0]["role"] == "user"

    def test_add_turn_assistant(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("assistant", "はい、こちらです")
        assert stm._turns[0]["role"] == "assistant"

    def test_add_turn_empty(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "")
        assert stm.turn_count == 0

    def test_add_turn_truncates_long(self, stm: ShortTermMemoryManager) -> None:
        long = "a" * 1000
        stm.add_turn("user", long)
        assert len(stm._turns[0]["content"]) == 500

    def test_add_turn_fifo_eviction(self, stm: ShortTermMemoryManager) -> None:
        stm2 = ShortTermMemoryManager(max_turns=2)
        stm2.add_turn("user", "first")
        stm2.add_turn("user", "second")
        stm2.add_turn("user", "third")
        assert stm2.turn_count == 2
        assert stm2._turns[0]["content"] == "second"
        assert stm2._turns[1]["content"] == "third"

    def test_add_turn_importance_marker(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "This is important")
        assert stm._turns[0]["importance"] >= 3

    def test_add_turn_importance_normal(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello")
        assert stm._turns[0]["importance"] == 0


class TestExtractEntities:
    def test_url(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "check https://example.com/path")
        assert "https://example.com/path" in stm._active_references

    def test_file_path(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "see /home/user/file.txt")
        assert "/home/user/file.txt" in stm._active_references

    def test_hashtag(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "topic #python")
        assert "#python" in stm._active_references

    def test_mention(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "ask @admin")
        assert "@admin" in stm._active_references

    def test_japanese_quote(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "「設定ファイル」を確認")
        assert "設定ファイル" in stm._active_references

    def test_camel_case(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "use ShortTermMemoryManager")
        assert "ShortTermMemoryManager" in stm._active_references

    def test_quoted_string(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", 'called "extract function"')
        assert "extract function" in stm._active_references


class TestSearch:
    def test_search_exact_word(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "I like Python programming")
        results = stm.search("Python", max_results=5)
        assert len(results) == 1
        assert results[0]["relevance"] > 0

    def test_search_no_match(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello world")
        results = stm.search("Python")
        assert len(results) == 0

    def test_search_multiple_turns(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "first about Python")
        stm.add_turn("user", "second about Java")
        stm.add_turn("user", "third about Python again")
        results = stm.search("Python")
        assert len(results) == 2

    def test_search_fallback_on_substring(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "PythonProgramming is great")
        results = stm.search("PythonProgramming", max_results=5)
        assert len(results) >= 1

    def test_search_respects_max_results(self, stm: ShortTermMemoryManager) -> None:
        for i in range(5):
            stm.add_turn("user", f"Python topic {i}")
        results = stm.search("Python", max_results=3)
        assert len(results) == 3

    def test_search_sorts_by_relevance(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello world")
        stm.add_turn("user", "Python is great")
        stm.add_turn("user", "I love Python and more Python")
        results = stm.search("Python")
        assert results[0]["relevance"] >= results[-1]["relevance"]


class TestSearchEntities:
    def test_find_matching_turn(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "check the error in server.log")
        results = stm.search_entities("server.log")
        assert len(results) == 1

    def test_no_match(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello")
        results = stm.search_entities("server")
        assert len(results) == 0

    def test_case_insensitive(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "Server Error")
        results = stm.search_entities("server")
        assert len(results) == 1


class TestRenderContext:
    def test_empty(self, stm: ShortTermMemoryManager) -> None:
        assert stm.render_context() == ""

    def test_basic(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello")
        result = stm.render_context()
        assert result == ""  # no topics/entities extracted from simple greeting

    def test_with_topics(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "Pythonの型ヒントについて教えて。使い方も知りたい。")
        result = stm.render_context()
        assert "### 現在の話題" in result

    def test_with_query_shows_relevant_first(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello world")
        stm.add_turn("user", "Python programming")
        result = stm.render_context(query="Python")
        assert "関連度" in result
        assert "hello world" in result or "Python" in result

    def test_max_chars(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "a" * 500)
        result = stm.render_context(max_chars=50)
        assert len(result) <= 53


class TestGetRecentTurns:
    def test_returns_last_n(self, stm: ShortTermMemoryManager) -> None:
        for i in range(5):
            stm.add_turn("user", f"turn {i}")
        recent = stm.get_recent_turns(3)
        assert len(recent) == 3
        assert recent[-1]["content"] == "turn 4"


class TestConsolidation:
    def test_mark_consolidated_all(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "a")
        stm.add_turn("user", "b")
        stm.mark_consolidated()
        assert all(t["consolidated"] for t in stm._turns)

    def test_mark_consolidated_partial(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "a")
        stm.add_turn("user", "b")
        stm.mark_consolidated(up_to_index=1)
        assert stm._turns[0]["consolidated"]
        assert not stm._turns[1]["consolidated"]

    def test_get_unconsolidated(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "a")
        stm.add_turn("user", "b")
        stm.mark_consolidated(up_to_index=1)
        un = stm.get_unconsolidated_turns()
        assert len(un) == 1
        assert un[0]["content"] == "b"

    def test_should_consolidate_when_full(self, stm: ShortTermMemoryManager) -> None:
        stm_full = ShortTermMemoryManager(max_turns=2)
        stm_full.add_turn("user", "a")
        assert not stm_full.should_consolidate()
        stm_full.add_turn("user", "b")
        assert stm_full.should_consolidate()


class TestClear:
    def test_clears_all(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "hello")
        stm.add_turn("user", "world")
        stm.clear()
        assert stm.turn_count == 0
        assert len(stm._current_topics) == 0
        assert len(stm._active_references) == 0


class TestTopics:
    def test_current_topics_updated(self, stm: ShortTermMemoryManager) -> None:
        stm.add_turn("user", "Pythonの型ヒントについて教えてください。使い方を知りたいです。")
        topics = stm.current_topics
        assert len(topics) > 0
        assert any("型ヒント" in t or "使い方" in t for t in topics)
