"""
CommandHandler — CLI コマンドの解釈・実行

以下のコマンドをサポートする:
  /help     - 利用可能なコマンド一覧を表示
  /sleep    - エージェントを一時休止状態に遷移
  /wakeup   - 休止状態から復帰
  /compact  - 会話履歴を強制要約
  /clear    - 会話履歴をクリア
  /status   - 現在の状態を表示
  /reflect  - セッション反省を強制実行
"""

from __future__ import annotations

import logging
from typing import Any

from iris.kernel.agent_state import AgentStateManager, State
from iris.kernel.services import ConversationService, ProactiveEngine

logger = logging.getLogger(__name__)

_COMMANDS: dict[str, str] = {
    "help": "利用可能なコマンド一覧を表示",
    "sleep": "エージェントを一時休止状態に遷移",
    "wakeup": "休止状態から復帰",
    "compact": "会話履歴を強制要約（履歴は保持）",
    "clear": "会話履歴を全てクリア",
    "status": "現在の状態を表示",
    "reflect": "セッション反省を強制実行",
}


class CommandHandler:
    """CLI コマンドの解釈と実行を行う。"""

    def __init__(
        self,
        state: AgentStateManager,
        conversation: ConversationService,
        proactive: ProactiveEngine,
    ) -> None:
        self._state = state
        self._conversation = conversation
        self._proactive = proactive

    def handle(self, text: str) -> str | None:
        """テキストがコマンドなら処理し、応答文字列を返す。非コマンドなら None を返す。"""
        if not text.startswith("/"):
            return None

        parts = text[1:].strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = {
            "help": self._cmd_help,
            "sleep": self._cmd_sleep,
            "wakeup": self._cmd_wakeup,
            "compact": self._cmd_compact,
            "clear": self._cmd_clear,
            "status": self._cmd_status,
            "reflect": self._cmd_reflect,
        }.get(cmd)

        if handler is None:
            return f"不明なコマンド: /{cmd}\n{self._cmd_help()}"

        return handler(args)

    def _cmd_help(self, _args: str = "") -> str:
        lines = ["利用可能なコマンド:"]
        for name, desc in _COMMANDS.items():
            lines.append(f"  /{name:<10} {desc}")
        return "\n".join(lines)

    def _cmd_sleep(self, _args: str = "") -> str:
        self._state.transition(State.SLEEPING)
        logger.info("Command: sleep")
        return "おやすみなさい。 /wakeup で起こしてください。"

    def _cmd_wakeup(self, _args: str = "") -> str:
        self._state.transition(State.IDLE)
        logger.info("Command: wakeup")
        return "おはようございます！"

    def _cmd_compact(self, _args: str = "") -> str:
        self._conversation.force_compact()
        logger.info("Command: compact")
        return "会話履歴を要約しました。"

    def _cmd_clear(self, _args: str = "") -> str:
        self._conversation.clear_history()
        logger.info("Command: clear")
        return "会話履歴を消去しました。"

    def _cmd_status(self, _args: str = "") -> str:
        state = self._state.current.value
        status = self._proactive.get_status()
        s: dict[str, Any] = status.get("suppression", {})
        return "\n".join(
            [
                f"状態: {state}",
                f"最終ユーザー活動: {s.get('last_user_activity', 0)}",
                f"最終自発発話: {s.get('last_proactive_time', 0)}",
                f"連続無視: {s.get('consecutive_ignores', 0)}",
                f"確認モード: {s.get('confirmation_mode', False)}",
                f"クールダウン中: {bool(s.get('cooldown_until', 0))}",
            ]
        )

    def _cmd_reflect(self, _args: str = "") -> str:
        try:
            self._conversation.session_reflect()
            logger.info("Command: reflect")
            return "反省を実行しました。"
        except Exception as e:
            logger.exception("Reflect command failed")
            return f"反省の実行中にエラーが発生しました: {e}"
