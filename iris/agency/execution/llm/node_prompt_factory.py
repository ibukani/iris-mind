from __future__ import annotations

from pathlib import Path

from langchain_core.messages import SystemMessage

_SITUATION_INSTRUCTIONS: dict[str, str] = {
    "proactive": (
        "## 状況: 自発的な一声\n"
        "時間帯や会話の流れに合わせて、自然に声をかけてください。\n"
        "誰かと会話しているのではなく、自ら会話を始める場面です。"
    ),
}

_RESPONSE_RULES = """## 回答ルール【厳守】
- 会話は簡潔に、1〜2文で十分。
- 敬語（です・ます・ください）は絶対に使用せず、親しみやすいタメ口（〜だよ、〜じゃん、〜だね）で話すこと。"""

_NODE_BASE_TEMPLATES: dict[str, str] = {
    "general_chat": "## 指示\n簡易な会話応答をおこなう。",
    "general_task": "",
    "setup": "",
}


class NodePromptFactory:
    """ノード固有指示の SystemMessage を構築する。

    Dual SystemMessage の [1] として使われる NodePrompt を担当。
    `.iris/config/node_prompts/{node_type}.md` が存在すれば
    そちらをベーステンプレートとして優先する。
    """

    def __init__(self, prompts_dir: str | None = None) -> None:
        self._prompts_dir = prompts_dir

    def build(
        self,
        node_type: str = "general_task",
        context_hint: str = "",
        situation: str = "",
    ) -> SystemMessage:
        base = self._load_base(node_type)

        parts: list[str] = []
        if base:
            parts.append(base)
        if context_hint:
            parts.append(f"## 会話コンテキスト\n{context_hint}")
        if situation in _SITUATION_INSTRUCTIONS:
            parts.append(_SITUATION_INSTRUCTIONS[situation])
        parts.append(_RESPONSE_RULES)

        return SystemMessage(content="\n\n".join(parts))

    def _load_base(self, node_type: str) -> str:
        if self._prompts_dir:
            path = Path(self._prompts_dir) / f"{node_type}.md"
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        return _NODE_BASE_TEMPLATES.get(node_type, "")
