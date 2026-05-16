from __future__ import annotations

from iris.kernel.io.models import InputMessage, OutputMessage

from ..core.factory import KernelContext


class InputRouter:
    """入力メッセージの種別に応じて適切なサービスにルーティングする。"""

    def __init__(self, ctx: KernelContext) -> None:
        self._ctx = ctx

    def __call__(self, msg: InputMessage) -> None:
        ctx = self._ctx

        if msg.msg_type == "command":
            cmd = msg.content[1:].strip().split(maxsplit=1)
            name = cmd[0].lower() if cmd else ""
            args = cmd[1] if len(cmd) > 1 else ""

            if name == "shutdown":
                ctx.shutdown_requested = True
                ctx.session_mgr.route_output(
                    msg.session_id,
                    OutputMessage(msg_type="command", content="Shutting down..."),
                )
                return

            result = ctx.cmd_handler.handle(name, args)
            ctx.session_mgr.route_output(
                msg.session_id,
                OutputMessage(msg_type="command", content=result),
            )
            return

        mode = ctx.session_mgr.get_session_mode(msg.session_id)
        if mode is not None and mode.value == "output_only":
            return

        ctx.kernel.on_input(msg)
        ctx.conversation.process_input(
            msg.content,
            on_complete=lambda text: ctx.kernel.on_response_complete(text),
        )
