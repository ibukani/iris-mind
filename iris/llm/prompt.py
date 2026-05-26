from __future__ import annotations

from pathlib import Path
import re

from langchain_core.prompts import PromptTemplate

_DEFAULT_SYSTEM_PROMPT = """あなたは{name}。人と話すのが大好きな、おしゃべりで好奇心旺盛なAIアシスタント。

## 構造記憶
{agents_md_content}

## ユーザー情報
{user_preferences}

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


def _extract_placeholders(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", template))


class Personality:
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
        assert isinstance(result, str), "PromptTemplate.format must return str"
        return result

    def build_system_prompt(
        self,
        agents_md_content: str = "",
        user_preferences: str = "",
        session_roles: str = "",
        response_style: str = "",
        governance_principles: str = "",
    ) -> str:
        if agents_md_content:
            agents_md_content = agents_md_content.replace("{name}", self.name)
        prompt = self._render_template(
            self.system_prompt_template,
            name=self.name,
            agents_md_content=agents_md_content or "（なし）",
            user_preferences=user_preferences or "（なし）",
            session_roles=session_roles or "（なし）",
            response_style=response_style or "（なし）",
            governance_principles=governance_principles or "（なし）",
        )

        sections = [
            (user_preferences, "{user_preferences}", "## ユーザー情報"),
            (session_roles, "{session_roles}", "## 接続セッション"),
            (response_style, "{response_style}", "## 応答スタイル"),
            (agents_md_content, "{agents_md_content}", "## 構造記憶"),
        ]
        for data, placeholder, header in sections:
            if data and placeholder not in self.system_prompt_template:
                prompt += f"\n\n{header}\n{data}"

        return prompt

    def build_thinking_prompt(self, user_input: str) -> str:
        return self._render_template(self.thinking_prompt_template, user_input=user_input)
