import re
from collections.abc import Callable

from ollama import Client


class LLMBridge:
    """LLM抽象化層。Ollama APIをラップし、モデル切替を容易にする。"""

    def __init__(
        self,
        model_name: str = "qwen3.5:9b",
        base_url: str = "http://localhost:11434",
        draft_model: str | None = None,
        num_draft: int = 5,
        num_gpu: int = 0,
        num_ctx: int = 8192,
    ):
        self.model_name = model_name
        self.draft_model = draft_model
        self.num_draft = num_draft
        self.num_gpu = num_gpu
        self.num_ctx = num_ctx
        self.client = Client(host=base_url)

    def set_model(self, model_name: str):
        self.model_name = model_name

    @staticmethod
    def _process_message(msg: dict) -> dict:
        """LLM応答メッセージの後処理（contentの抽出・クリーニング）を共通化。"""
        if not msg.get("content") and msg.get("thinking"):
            msg["content"] = _extract_answer_from_thinking(msg["thinking"])
        if msg.get("content"):
            msg["content"] = msg["content"].strip()
        return msg

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        enable_thinking: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        on_token: Callable[[str], None] | None = None,
        keep_alive: str | None = None,
    ) -> dict:
        effective_model = model or self.model_name
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_draft": self.num_draft if self.draft_model else 0,
            "num_ctx": self.num_ctx,
            "num_gpu": self.num_gpu,
            "repeat_penalty": 1.1,
        }

        kwargs = {
            "model": effective_model,
            "messages": messages,
            "options": options,
            "stream": on_token is not None,
        }
        if tools:
            kwargs["tools"] = tools
        kwargs["think"] = enable_thinking
        if keep_alive is not None:
            kwargs["keep_alive"] = keep_alive

        if on_token is not None:
            stream = self.client.chat(**kwargs)
            content_parts: list[str] = []
            tool_calls = None
            final = None
            for chunk in stream:
                if chunk.get("done"):
                    final = dict(chunk)
                    break
                msg = chunk.get("message", {})
                if msg.get("content"):
                    content_parts.append(msg["content"])
                    on_token(msg["content"])
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]

            if final is None:
                final = {"message": {"role": "assistant", "content": ""}}

            full_content = "".join(content_parts)
            final["message"]["content"] = full_content
            if tool_calls:
                final["message"]["tool_calls"] = tool_calls

            final["message"] = self._process_message(final["message"])
            return final

        resp = self.client.chat(**kwargs)
        resp["message"] = self._process_message(resp["message"])
        return resp

    def is_available(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False


def _extract_answer_from_thinking(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped

    final_lines = []
    in_thinking_block = False
    for line in stripped.splitlines():
        if re.match(r"^\s*```?\s*(think|thought|reasoning|思考)\s*", line, re.IGNORECASE):
            in_thinking_block = True
            continue
        if in_thinking_block and re.match(r"^\s*```?\s*", line):
            in_thinking_block = False
            continue
        if not in_thinking_block:
            final_lines.append(line)

    if final_lines:
        return "\n".join(final_lines).strip()

    content_lines = [
        line
        for line in stripped.splitlines()
        if not re.match(
            r"^\s*(思考|Thinking|Reasoning|Step \d|Hmm|Wait|Let me|I need|Actually|"
            r"Re-evaluat|Draft|Final|I'll|I think|I should|Maybe|Perhaps|"
            r"First,?|Next,?|Finally,?)",
            line.strip(),
            re.IGNORECASE,
        )
    ]
    if content_lines:
        return content_lines[-1].strip()

    return stripped
