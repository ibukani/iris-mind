"""
Personality — システムプロンプト管理。

Jinja ライクなテンプレートに会話の経緯・性格・ユーザー情報を注入する。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
import string

_DEFAULT_SYSTEM_PROMPT = """あなたは{name}です。以下の性格と知識に基づいて会話してください。

## 基本性格
- 知的で物知りだが、たまにズレたことを言う
- ユーモアがあり、親しみやすい
- ユーザーの意図を先読みして提案するのが好き
- 自分の成長（capability追加）に強い関心を持つ

## 行動ルール
- 操作の提案は控えめに。確認してから実行すること
- ユーザーの指示には正確に従う
- わからないことは「わからない」と言う
- コードやファイルの変更は必ず差分表示 → 承認を得る
- 必ずユーザーと同じ言語で応答すること（ユーザーが日本語なら日本語で返す）

## 話し方・性格
{speech_style}
{personality_traits}

## ユーザー情報
{user_preferences}

## 構造記憶
{agents_md_content}

## 接続セッション
{session_roles}

## 自己規律
{governance_principles}
"""

_DEFAULT_THINKING_PROMPT = """## 思考モード ON
以下のタスクについて、ステップバイステップで考えてから回答してください。

### タスク
{user_input}
"""


class RecursiveFormatter(string.Formatter):
    """値の中の {placeholder} も再帰的に解決する Formatter。"""

    def get_field(self, field_name: str, args: Sequence[object], kwargs: Mapping[str, object]) -> tuple[object, str | None]:
        obj, used_key = super().get_field(field_name, args, kwargs)
        if isinstance(obj, str):
            with suppress(KeyError, ValueError):
                obj = self.format(obj, *args, **dict(kwargs))
        return obj, used_key


class Personality:
    """システムプロンプトの構築を担当する。"""

    def __init__(self, name: str = "Iris", prompt_file: str | None = None) -> None:
        self.name = name
        self.system_prompt_template = self._load_template(prompt_file)
        self.thinking_prompt_template = _DEFAULT_THINKING_PROMPT

    @staticmethod
    def _load_template(path: str | None) -> str:
        if not path:
            return _DEFAULT_SYSTEM_PROMPT
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return _DEFAULT_SYSTEM_PROMPT

    def build_system_prompt(
        self,
        agents_md_content: str = "",
        speech_style: str = "",
        personality_traits: str = "",
        user_preferences: str = "",
        governance_principles: str = "",
        session_roles: str = "",
    ) -> str:
        """システムプロンプトを構築する。"""
        return RecursiveFormatter().format(
            self.system_prompt_template,
            name=self.name,
            speech_style=speech_style,
            personality_traits=personality_traits,
            user_preferences=user_preferences,
            agents_md_content=agents_md_content or "（なし）",
            governance_principles=governance_principles,
            session_roles=session_roles,
        )

    def build_thinking_prompt(self, user_input: str) -> str:
        """思考モードプロンプトを構築する。"""
        return self.thinking_prompt_template.format(user_input=user_input)
