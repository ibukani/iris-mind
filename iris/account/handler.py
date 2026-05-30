from __future__ import annotations

from typing import Any

from loguru import logger
import orjson

from iris.account.models import Account
from iris.account.provider import AccountProvider
from iris.event.event_types import ControlMessageEvent


class _AccountEventHandler:
    """Account 層のシステムメッセージハンドラ。"""

    def __init__(self, account_provider: AccountProvider, short_term: Any = None) -> None:
        self._provider = account_provider
        self._short_term = short_term

    def handle_control_message(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent | None:
        action = msg.action

        if action == "account.join":
            return self._handle_join(msg, session_id)
        if action == "account.leave":
            return self._handle_leave(msg, session_id)
        if action == "account.get":
            return self._handle_get(msg, session_id)
        if action == "account.update":
            return self._handle_update(msg, session_id)
        if action == "account.link_identity":
            return self._handle_link_identity(msg, session_id)

        logger.debug("AccountHandler: unhandled action={}", action)
        return None

    def handle_session_disconnect(self, session_id: str) -> None:
        """セッション配下の全ルームから退室させる。"""
        self._provider.unbind_all_for_session(session_id)

    def identify_message_speaker(
        self,
        session_id: str,
        identity: dict[str, Any] | None,
        room_id: str = "",
    ) -> tuple[str, str]:
        """発話者identityをaccount_idへ解決する。"""
        provider, subject, display_name, metadata = self._parse_identity(identity)
        if not provider or not subject:
            return "", ""

        account = self._provider.resolve_or_create_identity(
            provider,
            subject,
            display_name=display_name,
            metadata=metadata,
        )
        self._provider.bind_session(session_id, account.account_id, room_id=room_id)
        if self._short_term:
            self._short_term.add_user(account.account_id, account.nickname, session_id=session_id, room_id=room_id)
        return account.account_id, account.nickname

    def _handle_join(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        room_id = msg.room_id
        provider, subject, display_name, metadata = self._parse_identity(msg.identity)
        if not provider or not subject:
            return self._error("account.join", "identity.provider and identity.subject required")

        account = self._provider.resolve_or_create_identity(
            provider,
            subject,
            display_name=display_name or msg.nickname,
            metadata=metadata,
        )
        self._provider.bind_session(session_id, account.account_id, room_id=room_id)
        if self._short_term:
            self._short_term.add_user(account.account_id, account.nickname, session_id=session_id, room_id=room_id)

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.joined",
            account_id=account.account_id,
            room_id=room_id,
            nickname=account.nickname,
            identity=msg.identity,
            text=f"Joined: {account.nickname}",
        )

    def _handle_leave(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.leave", "not identified")

        self._provider.unbind_session(session_id, account.account_id, msg.room_id)
        if self._short_term:
            self._short_term.remove_user(account.account_id, session_id=session_id, room_id=msg.room_id)

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.left",
            account_id=account.account_id,
            room_id=msg.room_id,
            nickname=account.nickname,
            identity=msg.identity,
            text=f"Left: {account.nickname}",
        )

    def _handle_get(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._provider.get_account_by_session(session_id, msg.room_id)
        if not account:
            return self._error("account.get", "not identified")

        identities = [i.to_dict() for i in self._provider.get_identities(account.account_id)]
        data = account.to_dict()
        data["identities"] = identities
        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.profile",
            account_id=account.account_id,
            room_id=msg.room_id,
            nickname=account.nickname,
            text=orjson.dumps(data).decode("utf-8"),
        )

    def _handle_update(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.update", "not identified")

        if msg.nickname:
            self._provider.update_nickname(account.account_id, msg.nickname)
            account.nickname = msg.nickname
        if msg.profile:
            self._provider.update_profile(account.account_id, **msg.profile)
        if self._short_term:
            self._short_term.add_user(account.account_id, account.nickname, session_id=session_id, room_id=msg.room_id)

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.updated",
            account_id=account.account_id,
            room_id=msg.room_id,
            nickname=account.nickname,
            text=f"Updated: {account.nickname}",
        )

    def _handle_link_identity(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.link_identity", "not identified")

        provider, subject, display_name, metadata = self._parse_identity(msg.identity)
        if not provider or not subject:
            return self._error("account.link_identity", "identity.provider and identity.subject required")

        if not self._provider.link_identity(
            account.account_id,
            provider,
            subject,
            display_name=display_name,
            metadata=metadata,
        ):
            return self._error("account.link_identity", "identity already linked")

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.identity_linked",
            account_id=account.account_id,
            room_id=msg.room_id,
            nickname=account.nickname,
            identity=msg.identity,
            text=f"Linked identity: {provider}:{subject}",
        )

    def _resolve_target_account(self, msg: ControlMessageEvent, session_id: str) -> Account | None:
        if msg.account_id:
            account = self._provider.resolve(msg.account_id)
            if account is not None:
                return account

        provider, subject, _display_name, _metadata = self._parse_identity(msg.identity)
        if provider and subject:
            account = self._provider.get_account_by_identity(provider, subject)
            if account is not None:
                return account

        return self._provider.get_account_by_session(session_id, msg.room_id)

    @staticmethod
    def _parse_identity(identity: dict[str, Any] | None) -> tuple[str, str, str, dict[str, object]]:
        if not identity:
            return "", "", "", {}
        raw_metadata = identity.get("metadata", {})
        metadata: dict[str, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
        return (
            str(identity.get("provider", "")),
            str(identity.get("subject", "")),
            str(identity.get("display_name", "")),
            metadata,
        )

    @staticmethod
    def _error(action: str, message: str) -> ControlMessageEvent:
        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.error",
            text=f"Error: {message}",
            metadata={"request_action": action, "code": message.replace(" ", "_")},
        )
