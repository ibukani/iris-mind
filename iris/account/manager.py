from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from iris.account.events import (
    AccountCreatedEvent,
    AccountIdentityLinkedEvent,
    AccountUpdatedEvent,
)
from iris.account.models import Account, AccountIdentity, Provider
from iris.account.store import AccountStore


class AccountManager:
    """アカウント管理の核心サービス。

    責務:
    - アカウントのCRUD
    - 外部ID（provider + subject）との連携
    - EventBus へのイベント発行
    """

    def __init__(self, store: AccountStore, event_bus: Any = None) -> None:
        self._store = store
        self._event_bus = event_bus

    def register(self, display_name: str) -> Account:
        """新規アカウントを作成する。"""
        account = Account(display_name=display_name)
        self._store.add_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountCreatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account.account_id,
                    display_name=account.display_name,
                ),
            )

        return account

    def resolve(self, account_id: str) -> Account | None:
        """account_id からアカウントを取得する。"""
        return self._store.find_account_by_id(account_id)

    def resolve_display_name(self, account_id: str) -> str:
        """account_id から表示名を取得する。見つからない場合は account_id を返す。"""
        account = self.resolve(account_id)
        return account.display_name if account else account_id

    def get_account_by_identity(self, provider: Provider, subject: str) -> Account | None:
        """外部IDからアカウントを取得する。"""
        identity = self._store.find_identity(provider.value, subject)
        if identity is None:
            return None
        return self.resolve(identity.account_id)

    def resolve_or_create_identity(
        self,
        provider: Provider,
        subject: str,
        provider_name: str = "",
        metadata: dict[str, object] | None = None,
    ) -> Account:
        """外部IDからアカウントを解決し、なければ作成する。"""
        now = datetime.now(UTC).isoformat()
        identity = self._store.find_identity(provider.value, subject)
        if identity is not None:
            identity.provider_name = provider_name or identity.provider_name
            identity.metadata = metadata or identity.metadata
            identity.last_seen = now
            self._store.update_identity(identity)
            account = self.resolve(identity.account_id)
            if account is not None:
                account.last_seen = now
                if provider_name and not account.display_name:
                    account.display_name = provider_name
                self._store.update_account(account)
                return account

        account = self.register(provider_name or f"{provider.value}:{subject}")
        self.link_identity(account.account_id, provider, subject, provider_name=provider_name, metadata=metadata)
        return account

    def update_display_name(self, account_id: str, display_name: str) -> None:
        """表示名を更新する。"""
        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountManager: account not found: {}", account_id)
            return

        old = account.display_name
        account.display_name = display_name
        account.last_seen = datetime.now(UTC).isoformat()
        self._store.update_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountUpdatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account_id,
                    field_name="display_name",
                    old_value=old,
                    new_value=display_name,
                ),
            )

        logger.info("AccountManager: updated account_id={} display_name={}", account_id, display_name)

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
            logger.warning("AccountManager: account not found: {}", account_id)
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
        logger.info("AccountManager: updated profile for account_id={}", account_id)

    def link_identity(
        self,
        account_id: str,
        provider: Provider,
        subject: str,
        provider_name: str = "",
        metadata: dict[str, object] | None = None,
    ) -> bool:
        """外部IDを紐付ける。"""
        existing = self._store.find_identity(provider.value, subject)
        if existing and existing.account_id != account_id:
            logger.warning(
                "AccountManager: identity {}:{} already linked to account {}",
                provider.value,
                subject,
                existing.account_id,
            )
            return False

        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountManager: account not found: {}", account_id)
            return False

        now = datetime.now(UTC).isoformat()
        if existing:
            existing.provider_name = provider_name or existing.provider_name
            existing.metadata = metadata or existing.metadata
            existing.last_seen = now
            self._store.update_identity(existing)
        else:
            self._store.add_identity(
                AccountIdentity(
                    provider=provider,
                    subject=subject,
                    account_id=account_id,
                    provider_name=provider_name,
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
                    provider_name=provider_name,
                ),
            )

        logger.info("AccountManager: linked identity={}:{} account_id={}", provider.value, subject, account_id)
        return True

    def list_accounts(self) -> list[Account]:
        """全アカウント一覧を取得する。"""
        return self._store.load_accounts()

    def get_identities(self, account_id: str) -> list[AccountIdentity]:
        """アカウントに紐づく外部ID一覧を取得する。"""
        return self._store.find_identities_by_account(account_id)
