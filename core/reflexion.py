class Reflexion:
    """外側ループ。セッション終了時の振り返りと記憶更新を行う。"""

    def __init__(self):
        pass

    def reflect(self, conversation_history: list[dict]) -> dict:
        """会話履歴から教訓を抽出（LLM呼び出し結果を想定）"""
        return {
            "lesson": "",
            "preference": "",
            "improvement": "",
            "missing_capability": "",
        }

    def should_add_capability(self, reflection: dict) -> bool:
        return bool(reflection.get("missing_capability"))
