from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from iris.account.events import (
    AccountCreatedEvent,
    AccountIdentityLinkedEvent,
    AccountPresenceEvent,
    AccountSessionBoundEvent,
    AccountSessionUnboundEvent,
    AccountUpdatedEvent,
)
from iris.account.models import Account, AccountIdentity, SessionBinding
from iris.account.store import AccountStore


class AccountProvider:
    """アカウント管理の核心サービス。

    責務:
    - アカウントのCRUD
    - 外部ID（provider + subject）との連携
    - セッション ↔ アカウントの紐付け
    - EventBus へのイベント発行
    """

    def __init__(self, store: AccountStore, event_bus: Any = None) -> None:
        self._store = store
        self._event_bus = event_bus

    def register(self, nickname: str) -> Account:
        """新規アカウントを作成する。"""
        account = Account(nickname=nickname)
        self._store.add_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountCreatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account.account_id,
                    nickname=account.nickname,
                ),
            )

        return account

    def resolve(self, account_id: str) -> Account | None:
        """account_id からアカウントを取得する。"""
        return self._store.find_account_by_id(account_id)

    def resolve_nickname(self, account_id: str) -> str:
        """account_id からニックネームを取得する。見つからない場合は account_id を返す。"""
        account = self.resolve(account_id)
        return account.nickname if account else account_id

    def get_account_by_identity(self, provider: str, subject: str) -> Account | None:
        """外部IDからアカウントを取得する。"""
        identity = self._store.find_identity(provider, subject)
        if identity is None:
            return None
        return self.resolve(identity.account_id)

    def resolve_or_create_identity(
        self,
        provider: str,
        subject: str,
        display_name: str = "",
        metadata: dict[str, object] | None = None,
    ) -> Account:
        """外部IDからアカウントを解決し、なければ作成する。"""
        now = datetime.now(UTC).isoformat()
        identity = self._store.find_identity(provider, subject)
        if identity is not None:
            identity.display_name = display_name or identity.display_name
            identity.metadata = metadata or identity.metadata
            identity.last_seen = now
            self._store.update_identity(identity)
            account = self.resolve(identity.account_id)
            if account is not None:
                account.last_seen = now
                if display_name and not account.nickname:
                    account.nickname = display_name
                self._store.update_account(account)
                return account

        account = self.register(display_name or f"{provider}:{subject}")
        self.link_identity(account.account_id, provider, subject, display_name=display_name, metadata=metadata)
        return account

    def update_nickname(self, account_id: str, nickname: str) -> None:
        """ニックネームを更新する。"""
        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountProvider: account not found: {}", account_id)
            return

        old = account.nickname
        account.nickname = nickname
        account.last_seen = datetime.now(UTC).isoformat()
        self._store.update_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountUpdatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account_id,
                    field_name="nickname",
                    old_value=old,
                    new_value=nickname,
                ),
            )

        logger.info("AccountProvider: updated account_id={} nickname={}", account_id, nickname)

    def update_last_seen(self, account_id: str) -> None:
        """last_seen を更新する。"""
        account = self.resolve(account_id)
        if not account:
            return
        account.last_seen = datetime.now(UTC).isoformat()
        self._store.update_account(account)

    def update_profile(self, account_id: str, **fields: Any) -> None:
        """プロフィールフィールドを更新する。"""
        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountProvider: account not found: {}", account_id)
            return

        for key, value in fields.items():
            old = account.profile.get(key)
            account.profile[key] = value
            if self._event_bus:
                self._event_bus.publish(
                    AccountUpdatedEvent(
                        timestamp=datetime.now(UTC),
                        source="account",
                        account_id=account_id,
                        field_name=f"profile.{key}",
                        old_value=old,
                        new_value=value,
                    ),
                )

        account.last_seen = datetime.now(UTC).isoformat()
        self._store.update_account(account)
        logger.info("AccountProvider: updated profile for account_id={}", account_id)

    def link_identity(
        self,
        account_id: str,
        provider: str,
        subject: str,
        display_name: str = "",
        metadata: dict[str, object] | None = None,
    ) -> bool:
        """外部IDを紐付ける。"""
        existing = self._store.find_identity(provider, subject)
        if existing and existing.account_id != account_id:
            logger.warning(
                "AccountProvider: identity {}:{} already linked to account {}",
                provider,
                subject,
                existing.account_id,
            )
            return False

        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountProvider: account not found: {}", account_id)
            return False

        now = datetime.now(UTC).isoformat()
        if existing:
            existing.display_name = display_name or existing.display_name
            existing.metadata = metadata or existing.metadata
            existing.last_seen = now
            self._store.update_identity(existing)
        else:
            self._store.add_identity(
                AccountIdentity(
                    provider=provider,
                    subject=subject,
                    account_id=account_id,
                    display_name=display_name,
                    metadata=metadata or {},
                    last_seen=now,
                ),
            )

        if self._event_bus:
            self._event_bus.publish(
                AccountIdentityLinkedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account_id,
                    provider=provider,
                    subject=subject,
                    display_name=display_name,
                ),
            )

        logger.info("AccountProvider: linked identity={}:{} account_id={}", provider, subject, account_id)
        return True

    def bind_session(self, session_id: str, account_id: str) -> None:
        """セッションとアカウントを紐付ける。"""
        existing = self._store.find_active_binding(session_id)
        if existing is not None and existing.account_id == account_id:
            return
        binding = SessionBinding(session_id=session_id, account_id=account_id)
        self._store.add_binding(binding)

        if self._event_bus:
            self._event_bus.publish(
                AccountSessionBoundEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    session_id=session_id,
                    account_id=account_id,
                ),
            )
            account = self.resolve(account_id)
            provider, subject = self._presence_identity(account_id)
            self._event_bus.publish(
                AccountPresenceEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    session_id=session_id,
                    account_id=account_id,
                    nickname=account.nickname if account else account_id,
                    state="entered",
                    provider=provider,
                    subject=subject,
                ),
            )

        logger.debug("AccountProvider: bound session={} to account={}", session_id, account_id)

    def unbind_session(self, session_id: str, account_id: str | None = None) -> str | None:
        """セッションの紐付けを解除し、account_id を返す。"""
        binding = (
            self._store.find_active_binding_for_account(session_id, account_id)
            if account_id
            else self._store.find_active_binding(session_id)
        )
        if not binding:
            return None

        binding.disconnected_at = datetime.now(UTC).isoformat()
        self._store.update_binding(binding)

        if self._event_bus:
            self._event_bus.publish(
                AccountSessionUnboundEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    session_id=session_id,
                    account_id=binding.account_id,
                ),
            )
            account = self.resolve(binding.account_id)
            provider, subject = self._presence_identity(binding.account_id)
            self._event_bus.publish(
                AccountPresenceEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    session_id=session_id,
                    account_id=binding.account_id,
                    nickname=account.nickname if account else binding.account_id,
                    state="left",
                    provider=provider,
                    subject=subject,
                ),
            )

        logger.debug("AccountProvider: unbound session={}", session_id)
        return binding.account_id

    def get_account_by_session(self, session_id: str) -> Account | None:
        """セッションからアカウントを取得する。"""
        binding = self._store.find_active_binding(session_id)
        if not binding:
            return None
        return self.resolve(binding.account_id)

    def get_active_accounts(self) -> list[Account]:
        """アクティブなアカウント一覧を取得する。"""
        bindings = [b for b in self._store.load_bindings() if b.disconnected_at is None]
        account_ids = {b.account_id for b in bindings}
        accounts = []
        for aid in account_ids:
            a = self.resolve(aid)
            if a:
                accounts.append(a)
        return accounts

    def list_accounts(self) -> list[Account]:
        """全アカウント一覧を取得する。"""
        return self._store.load_accounts()

    def get_identities(self, account_id: str) -> list[AccountIdentity]:
        """アカウントに紐づく外部ID一覧を取得する。"""
        return self._store.find_identities_by_account(account_id)

    def _presence_identity(self, account_id: str) -> tuple[str, str]:
        identities = self._store.find_identities_by_account(account_id)
        if not identities:
            return "", ""
        identity = identities[0]
        return identity.provider, identity.subject
