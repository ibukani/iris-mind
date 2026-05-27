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

    @staticmethod
    def _split_sections(template: str) -> list[str]:
        """## 見出しで区切ったセクションリスト。[0]はヘッダ行。"""
        lines = template.split("\n")
        sections: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("## ") and current:
                sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))
        return sections

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

        content_map = {
            "{agents_md_content}": agents_md_content,
            "{user_preferences}": user_preferences,
            "{session_roles}": session_roles,
            "{governance_principles}": governance_principles,
            "{response_style}": response_style,
        }

        template = self.system_prompt_template
        sections = self._split_sections(template)
        filtered: list[str] = [sections[0]]
        for sec in sections[1:]:
            keep = True
            for ph, val in content_map.items():
                if ph in sec and not val:
                    keep = False
                    break
            if keep:
                filtered.append(sec)

        prompt = self._render_template(
            "\n".join(filtered),
            name=self.name,
            agents_md_content=agents_md_content or "",
            user_preferences=user_preferences or "",
            session_roles=session_roles or "",
            response_style=response_style or "",
            governance_principles=governance_principles or "",
        )

        for data, placeholder, header in [
            (user_preferences, "{user_preferences}", "## ユーザー情報"),
            (session_roles, "{session_roles}", "## 接続セッション"),
            (response_style, "{response_style}", "## 応答スタイル"),
            (agents_md_content, "{agents_md_content}", "## 構造記憶"),
        ]:
            if data and placeholder not in template:
                prompt += f"\n\n{header}\n{data}"

        return prompt.strip()

    def build_thinking_prompt(self, user_input: str) -> str:
        return self._render_template(self.thinking_prompt_template, user_input=user_input)
