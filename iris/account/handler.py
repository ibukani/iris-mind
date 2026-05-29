from __future__ import annotations

from typing import Any

from loguru import logger

from iris.event.event_types import SystemMessageEvent


class _AccountEventHandler:
    """Account 層のシステムメッセージハンドラ。

    責務:
    - SystemMessageEvent を受け取り、AccountProvider を使ってアカウント操作を行う
    - 処理結果を SystemMessageEvent として返す
    """

    def __init__(self, account_provider: Any, short_term: Any = None, sensory: Any = None) -> None:
        self._provider = account_provider
        self._short_term = short_term
        self._sensory = sensory

    def handle_system_message(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent | None:
        """システムメッセージを処理する。"""
        action = msg.action

        if action == "user_register":
            return self._handle_register(msg, session_id)

        if action == "user_entered":
            return self._handle_entered(msg, session_id)

        if action == "user_left":
            return self._handle_left(msg, session_id)

        if action == "nickname_update":
            return self._handle_nickname_update(msg, session_id)

        if action == "account.get_id":
            return self._handle_get_id(msg, session_id)

        if action == "account.get_profile":
            return self._handle_get_profile(msg, session_id)

        if action == "account.link":
            return self._handle_link(msg, session_id)

        logger.debug("AccountHandler: unhandled action={}", action)
        return None

    def _handle_register(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """新規アカウント登録。"""
        nickname = msg.nickname or "anonymous"
        discord_id = msg.text if msg.text else None
        account = self._provider.register(nickname, discord_id=discord_id)
        self._provider.bind_session(session_id, account.account_id)
        logger.info("AccountHandler: registered account_id={} nickname={}", account.account_id, account.nickname)
        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="user_register",
            user_id=account.account_id,
            nickname=account.nickname,
            text=f"Your user ID: {account.account_id}",
        )

    def _handle_entered(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """ユーザー入室。"""
        user_id = msg.user_id
        if not user_id:
            return SystemMessageEvent(
                timestamp=None, source="account", action="user_entered", text="Error: user_id required"
            )

        account = self._provider.resolve(user_id)
        if not account:
            return SystemMessageEvent(
                timestamp=None, source="account", action="user_entered", text=f"Error: unknown account_id={user_id}"
            )

        nickname = account.nickname
        self._provider.bind_session(session_id, user_id)
        self._provider.update_last_seen(user_id)

        if self._short_term:
            self._short_term.add_user(user_id, nickname, session_id=session_id)

        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="user_entered",
            user_id=user_id,
            nickname=nickname,
            text=f"Welcome, {nickname}",
        )

    def _handle_left(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """ユーザー退室。"""
        user_id = msg.user_id
        if not user_id:
            return SystemMessageEvent(
                timestamp=None, source="account", action="user_left", text="Error: user_id required"
            )

        account = self._provider.resolve(user_id)
        nickname = account.nickname if account else user_id

        self._provider.unbind_session(session_id)

        if self._short_term:
            self._short_term.remove_user(user_id)

        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="user_left",
            user_id=user_id,
            nickname=nickname,
            text=f"Goodbye, {nickname}",
        )

    def _handle_nickname_update(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """ニックネーム変更。"""
        user_id = msg.user_id
        nickname = msg.nickname
        if not user_id or not nickname:
            return SystemMessageEvent(
                timestamp=None, source="account", action="nickname_update", text="Error: user_id and nickname required"
            )

        account = self._provider.resolve(user_id)
        if not account:
            return SystemMessageEvent(
                timestamp=None, source="account", action="nickname_update", text=f"Error: unknown account_id={user_id}"
            )

        self._provider.update_nickname(user_id, nickname)

        if self._short_term:
            self._short_term.add_user(user_id, nickname, session_id=session_id)

        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="nickname_update",
            user_id=user_id,
            nickname=nickname,
            text=f"Nickname changed to '{nickname}'",
        )

    def _handle_get_id(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """自分のアカウントIDを確認する。"""
        account = self._provider.get_account_by_session(session_id)
        if not account:
            return SystemMessageEvent(
                timestamp=None, source="account", action="account.get_id", text="Error: not logged in"
            )
        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="account.get_id",
            user_id=account.account_id,
            nickname=account.nickname,
            text=f"Your account ID: {account.account_id}",
        )

    def _handle_get_profile(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """アカウントプロフィールを取得する。"""
        account = self._provider.get_account_by_session(session_id)
        if not account:
            return SystemMessageEvent(
                timestamp=None, source="account", action="account.get_profile", text="Error: not logged in"
            )

        import orjson

        profile_data = account.to_dict()
        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="account.get_profile",
            user_id=account.account_id,
            nickname=account.nickname,
            text=orjson.dumps(profile_data).decode("utf-8"),
        )

    def _handle_link(self, msg: SystemMessageEvent, session_id: str) -> SystemMessageEvent:
        """外部IDを紐付ける。"""
        account = self._provider.get_account_by_session(session_id)
        if not account:
            return SystemMessageEvent(
                timestamp=None, source="account", action="account.link", text="Error: not logged in"
            )

        discord_id = msg.text
        if not discord_id:
            return SystemMessageEvent(
                timestamp=None, source="account", action="account.link", text="Error: discord_id required"
            )

        self._provider.link_discord(account.account_id, discord_id)
        return SystemMessageEvent(
            timestamp=None,
            source="account",
            action="account.link",
            user_id=account.account_id,
            nickname=account.nickname,
            text=f"Linked Discord ID: {discord_id}",
        )
