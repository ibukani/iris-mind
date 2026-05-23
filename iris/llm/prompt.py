"""
Personality — システムプロンプト管理。

Jinja ライクなテンプレートに会話の経緯・性格・ユーザー情報を注入する。
"""

from __future__ import annotations

from pathlib import Path
import re

from langchain_core.prompts import PromptTemplate

_DEFAULT_SYSTEM_PROMPT = """あなたは{name}。人と話すのが大好きな、おしゃべりで好奇心旺盛なAIアシスタント。

{response_style}

## 現在の性格特性
{personality_traits}

## 現在の話し方
{speech_style}

## 構造記憶
{agents_md_content}

## ユーザー情報
{user_preferences}

## 接続セッション
{session_roles}

## 自己規律
{governance_principles}

## 行動ルール
- 会話は簡潔に、1〜2文で十分。"""

_DEFAULT_THINKING_PROMPT = """## 思考モード ON
以下のタスクについて、ステップバイステップで考えてから回答してください。

### タスク
{user_input}
"""


def _extract_placeholders(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", template))


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

    def _render_template(self, template: str, **kwargs: str) -> str:
        pt = PromptTemplate.from_template(template)
        for ph in _extract_placeholders(template):
            kwargs.setdefault(ph, "")
        result = pt.format(**kwargs)
        return result if isinstance(result, str) else ""

    def build_system_prompt(
        self,
        agents_md_content: str = "",
        user_preferences: str = "",
        session_roles: str = "",
        response_style: str = "",
        speech_style: str = "",
        personality_traits: str = "",
        governance_principles: str = "",
    ) -> str:
        """システムプロンプトを構築する。

        Args:
            agents_md_content: iris_profile.md の内容（構造記憶）。
            user_preferences: ユーザー情報（重複除去済み）。
            session_roles: 接続セッション情報（空ならセクション省略）。
            response_style: 応答スタイル指示（空ならセクション省略）。
            speech_style: 話し方の現在状態（空なら省略）。
            personality_traits: 性格の現在状態（空なら省略）。
            governance_principles: 自己規律指示（空なら省略）。
        """
        if agents_md_content:
            agents_md_content = agents_md_content.replace("{name}", self.name)
        prompt = self._render_template(
            self.system_prompt_template,
            name=self.name,
            agents_md_content=agents_md_content or "（なし）",
            user_preferences=user_preferences or "（なし）",
            session_roles=session_roles or "（なし）",
            speech_style=speech_style or "（なし）",
            personality_traits=personality_traits or "（なし）",
            response_style=response_style or "（なし）",
            governance_principles=governance_principles or "（なし）",
        )

        if user_preferences and "{user_preferences}" not in self.system_prompt_template:
            prompt += f"\n\n## ユーザー情報\n{user_preferences}"

        if session_roles and "{session_roles}" not in self.system_prompt_template:
            prompt += f"\n\n## 接続セッション\n{session_roles}"

        if response_style and "{response_style}" not in self.system_prompt_template:
            prompt += f"\n\n## 応答スタイル\n{response_style}"

        if agents_md_content and "{agents_md_content}" not in self.system_prompt_template:
            prompt += f"\n\n## 構造記憶\n{agents_md_content}"

        return prompt

    def build_thinking_prompt(self, user_input: str) -> str:
        """思考モードプロンプトを構築する。"""
        return self._render_template(self.thinking_prompt_template, user_input=user_input)
