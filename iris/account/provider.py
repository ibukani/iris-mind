from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from iris.account.events import (
    AccountCreatedEvent,
    AccountSessionBoundEvent,
    AccountSessionUnboundEvent,
    AccountUpdatedEvent,
)
from iris.account.models import Account, SessionBinding
from iris.account.store import AccountStore


class AccountProvider:
    """アカウント管理の核心サービス。

    責務:
    - アカウントのCRUD
    - 外部ID（discord_id）との連携
    - セッション ↔ アカウントの紐付け
    - EventBus へのイベント発行
    """

    def __init__(self, store: AccountStore, event_bus: Any = None) -> None:
        self._store = store
        self._event_bus = event_bus

    def register(self, nickname: str, discord_id: str | None = None) -> Account:
        """新規アカウントを作成する。"""
        if discord_id:
            existing = self._store.find_account_by_discord_id(discord_id)
            if existing:
                logger.info(
                    "AccountProvider: discord_id {} already mapped to account {}",
                    discord_id,
                    existing.account_id,
                )
                return existing

        account = Account(nickname=nickname, discord_id=discord_id)
        self._store.add_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountCreatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account.account_id,
                    nickname=account.nickname,
                    discord_id=account.discord_id,
                ),
            )

        return account

    def resolve(self, account_id: str) -> Account | None:
        """account_id からアカウントを取得する。"""
        return self._store.find_account_by_id(account_id)

    def resolve_by_discord_id(self, discord_id: str) -> Account | None:
        """discord_id からアカウントを取得する。"""
        return self._store.find_account_by_discord_id(discord_id)

    def resolve_nickname(self, account_id: str) -> str:
        """account_id からニックネームを取得する。見つからない場合は account_id を返す。"""
        account = self.resolve(account_id)
        return account.nickname if account else account_id

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

    def link_discord(self, account_id: str, discord_id: str) -> None:
        """discord_id を紐付ける。"""
        existing = self._store.find_account_by_discord_id(discord_id)
        if existing and existing.account_id != account_id:
            logger.warning(
                "AccountProvider: discord_id {} already linked to account {}",
                discord_id,
                existing.account_id,
            )
            return

        account = self.resolve(account_id)
        if not account:
            logger.warning("AccountProvider: account not found: {}", account_id)
            return

        old = account.discord_id
        account.discord_id = discord_id
        account.last_seen = datetime.now(UTC).isoformat()
        self._store.update_account(account)

        if self._event_bus:
            self._event_bus.publish(
                AccountUpdatedEvent(
                    timestamp=datetime.now(UTC),
                    source="account",
                    account_id=account_id,
                    field_name="discord_id",
                    old_value=old,
                    new_value=discord_id,
                ),
            )

        logger.info("AccountProvider: linked discord_id={} to account_id={}", discord_id, account_id)

    def bind_session(self, session_id: str, account_id: str) -> None:
        """セッションとアカウントを紐付ける。"""
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

        logger.debug("AccountProvider: bound session={} to account={}", session_id, account_id)

    def unbind_session(self, session_id: str) -> str | None:
        """セッションの紐付けを解除し、account_id を返す。"""
        binding = self._store.find_active_binding(session_id)
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
