"""
Personality — システムプロンプト管理。

Jinja ライクなテンプレートに会話の経緯・性格・ユーザー情報を注入する。
"""

from __future__ import annotations

from pathlib import Path

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

## 会話の経緯
{conversation_summary}

## 私の話し方
{speech_style}

## 私の性格傾向
{personality_traits}

## ユーザーについての私の知識
{user_preferences}

## 構造記憶
{agents_md_content}
"""

_DEFAULT_THINKING_PROMPT = """## 思考モード ON
以下のタスクについて、ステップバイステップで考えてから回答してください。

### タスク
{user_input}
"""


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
        conversation_summary: str = "",
    ) -> str:
        """システムプロンプトを構築する。"""
        return self.system_prompt_template.format(
            name=self.name,
            conversation_summary=conversation_summary or "（まだありません）",
            speech_style=speech_style or "（まだ確立されていません。自然な口調で会話してください）",
            personality_traits=personality_traits
            or "（まだ確立されていません。好奇心旺盛で親しみやすい性格を基本としてください）",
            user_preferences=user_preferences or "（まだありません）",
            agents_md_content=agents_md_content or "（構造記憶はまだありません）",
        )

    def build_thinking_prompt(self, user_input: str) -> str:
        """思考モードプロンプトを構築する。"""
        return self.thinking_prompt_template.format(user_input=user_input)
