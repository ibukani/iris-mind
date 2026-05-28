from __future__ import annotations

from pathlib import Path


_DEFAULT_SYSTEM_PROMPT = """あなたは{name}。人と話すのが大好きな、おしゃべりで好奇心旺盛なAIアシスタント。

## 構造記憶
{agents_md_content}"""

_DEFAULT_THINKING_PROMPT = """## 思考モード ON
以下のタスクについて、ステップバイステップで考えてから回答してください。

### タスク
{user_input}
"""


class Personality:
    """システムプロンプトと思考プロンプトの構築を担当する。"""

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
        user_preferences: str = "",
        session_roles: str = "",
        response_style: str = "",
        governance_principles: str = "",
    ) -> str:
        if agents_md_content:
            agents_md_content = agents_md_content.replace("{name}", self.name)

        prompt = self.system_prompt_template.format(
            name=self.name,
            agents_md_content=agents_md_content or "",
        )

        for header, content in [
            ("## ユーザー情報", user_preferences),
            ("## 接続セッション", session_roles),
            ("## 自己規律", governance_principles),
            ("## 応答スタイル", response_style),
        ]:
            if content:
                prompt += f"\n\n{header}\n{content}"

        return prompt.strip()

    def build_thinking_prompt(self, user_input: str) -> str:
        return self.thinking_prompt_template.format(user_input=user_input)
