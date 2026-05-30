from __future__ import annotations

from typing import Any

from loguru import logger
import orjson

from iris.event.event_types import ControlMessageEvent


class _AccountDispatcher:
    """アカウント管理のControlMessage振り分け＋レスポンス構築。

    責務:
    - action文字列ルーティング
    - 入力検証
    - ControlMessageEvent レスポンス構築
    """

    def __init__(self, account_manager: Any) -> None:
        self._account_manager = account_manager

    def handle_control_message(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent | None:
        action = msg.action

        if action == "account.identify":
            return self._handle_identify(msg, session_id)
        if action == "account.profile":
            return self._handle_profile(msg, session_id)
        if action == "account.update":
            return self._handle_update(msg, session_id)
        if action == "account.link":
            return self._handle_link(msg, session_id)

        logger.debug("AccountDispatcher: unhandled action={}", action)
        return None

    def identify_message_speaker(
        self,
        session_id: str,
        identity: dict[str, Any] | None,
    ) -> tuple[str, str]:
        provider, subject, provider_name, metadata = self._parse_identity(identity)
        if not provider or not subject:
            return "", ""

        account = self._account_manager.resolve_or_create_identity(
            provider,
            subject,
            provider_name=provider_name,
            metadata=metadata,
        )
        return account.account_id, account.display_name

    def _handle_identify(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        provider, subject, provider_name, metadata = self._parse_identity(msg.identity)
        if not provider or not subject:
            return self._error("account.identify", "identity.provider and identity.subject required")

        account = self._account_manager.resolve_or_create_identity(
            provider,
            subject,
            provider_name=provider_name or msg.display_name,
            metadata=metadata,
        )

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.identified",
            account_id=account.account_id,
            display_name=account.display_name,
            identity=msg.identity,
            text=f"Identified: {account.display_name}",
        )

    def _handle_profile(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.profile", "not identified")

        identities = [i.to_dict() for i in self._account_manager.get_identities(account.account_id)]
        data = account.to_dict()
        data["identities"] = identities
        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.profile",
            account_id=account.account_id,
            display_name=account.display_name,
            text=orjson.dumps(data).decode("utf-8"),
        )

    def _handle_update(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.update", "not identified")

        if msg.display_name:
            self._account_manager.update_display_name(account.account_id, msg.display_name)
            account.display_name = msg.display_name
        if msg.profile:
            self._account_manager.update_profile(account.account_id, **msg.profile)

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.updated",
            account_id=account.account_id,
            display_name=account.display_name,
            text=f"Updated: {account.display_name}",
        )

    def _handle_link(self, msg: ControlMessageEvent, session_id: str) -> ControlMessageEvent:
        account = self._resolve_target_account(msg, session_id)
        if account is None:
            return self._error("account.link", "not identified")

        provider, subject, provider_name, metadata = self._parse_identity(msg.identity)
        if not provider or not subject:
            return self._error("account.link", "identity.provider and identity.subject required")

        if not self._account_manager.link_identity(
            account.account_id,
            provider,
            subject,
            provider_name=provider_name,
            metadata=metadata,
        ):
            return self._error("account.link", "identity already linked")

        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action="account.linked",
            account_id=account.account_id,
            display_name=account.display_name,
            identity=msg.identity,
            text=f"Linked identity: {provider}:{subject}",
        )

    def _resolve_target_account(self, msg: ControlMessageEvent, session_id: str) -> Any:
        if msg.account_id:
            account = self._account_manager.resolve(msg.account_id)
            if account is not None:
                return account

        provider, subject, _provider_name, _metadata = self._parse_identity(msg.identity)
        if provider and subject:
            account = self._account_manager.get_account_by_identity(provider, subject)
            if account is not None:
                return account

        return None

    @staticmethod
    def _parse_identity(identity: dict[str, Any] | None) -> tuple[str, str, str, dict[str, object]]:
        if not identity:
            return "", "", "", {}
        raw_metadata = identity.get("metadata", {})
        metadata: dict[str, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
        return (
            str(identity.get("provider", "")),
            str(identity.get("subject", "")),
            str(identity.get("provider_name", "")),
            metadata,
        )

    @staticmethod
    def _error(action: str, message: str) -> ControlMessageEvent:
        return ControlMessageEvent(
            timestamp=None,
            source="account",
            action=action,
            text=f"Error: {message}",
        )
