from __future__ import annotations

import os
from pathlib import Path
import tempfile

from iris.llm.prompt import Personality


def test_default_prompt() -> None:
    pers = Personality(name="IrisTest")
    prompt = pers.build_system_prompt(
        agents_md_content="構造記憶テスト",
        user_preferences="ユーザー設定テスト",
        session_roles="セッションテスト",
        response_style="応答スタイルテスト",
    )
    assert "IrisTest" in prompt
    assert "構造記憶テスト" in prompt
    assert "ユーザー設定テスト" in prompt
    assert "セッションテスト" in prompt
    assert "応答スタイルテスト" in prompt


def test_custom_template_placeholders() -> None:
    template_content = """あなたは{name}です。
話し方: {speech_style}
性格: {personality_traits}
規律: {governance_principles}
ユーザー: {user_preferences}
セッション: {session_roles}
記憶: {agents_md_content}
存在しないキー: {unknown_placeholder}
"""
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        Path(path).write_text(template_content, encoding="utf-8")
        pers = Personality(name="IrisCustom", prompt_file=path)
        prompt = pers.build_system_prompt(
            agents_md_content="構造記憶カスタム",
            user_preferences="ユーザーカスタム",
            session_roles="セッションカスタム",
            speech_style="話し方カスタム",
            personality_traits="性格カスタム",
            governance_principles="規律カスタム",
        )
        assert "IrisCustom" in prompt
        assert "話し方カスタム" in prompt
        assert "性格カスタム" in prompt
        assert "規律カスタム" in prompt
        assert "ユーザーカスタム" in prompt
        assert "セッションカスタム" in prompt
        assert "構造記憶カスタム" in prompt
        # unknown_placeholder は空文字列に置換され、KeyErrorにならないことを確認
        assert "{unknown_placeholder}" not in prompt
    finally:
        p = Path(path)
        if p.exists():
            os.unlink(path)
