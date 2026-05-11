import re

from ollama import Client


class LLMBridge:
    """LLM抽象化層。Ollama APIをラップし、モデル切替を容易にする。"""

    def __init__(self, model_name: str = "qwen3.5:9b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.client = Client(host=base_url)

    def set_model(self, model_name: str):
        self.model_name = model_name

    def chat(
        self,
        messages: list[dict],
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> dict:
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }

        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "options": options,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
        kwargs["think"] = enable_thinking

        resp = self.client.chat(**kwargs)

        msg = resp["message"]
        if not msg.content and msg.thinking:
            msg.content = _extract_answer_from_thinking(msg.thinking)
        if msg.content:
            msg.content = msg.content.strip()

        return resp

    def is_available(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False


def _extract_answer_from_thinking(text: str) -> str:
    lines = text.strip().splitlines()
    non_thinking = [l for l in lines if not re.match(
        r"^\s*(思考|Thinking|Reasoning|Step|Hmm|Wait|Let|I need|Actually|Re-evaluat|Draft|Final Decision)",
        l.strip()
    )]
    if non_thinking:
        return non_thinking[-1].strip()
    return text.strip()
