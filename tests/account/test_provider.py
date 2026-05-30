from __future__ import annotations

from pathlib import Path

import pytest

from iris.account.manager import AccountManager
from iris.account.store import AccountStore
from iris.event import EventBus


@pytest.fixture
def provider(tmp_path: Path) -> AccountManager:
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
    )
    return AccountManager(store=store, event_bus=EventBus())


@pytest.fixture
def provider_and_bus(tmp_path: Path) -> tuple[AccountManager, EventBus]:
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
    )
    bus = EventBus()
    return AccountManager(store=store, event_bus=bus), bus


class TestRegister:
    def test_register_creates_account(self, provider: AccountManager) -> None:
        a = provider.register("alice")
        assert a.nickname == "alice"
        assert len(a.account_id) == 16


class TestIdentity:
    def test_resolve_or_create_identity_creates_account(self, provider: AccountManager) -> None:
        account = provider.resolve_or_create_identity("discord", "123", display_name="Bob")
        assert account.nickname == "Bob"
        found = provider.get_account_by_identity("discord", "123")
        assert found is not None
        assert found.account_id == account.account_id

    def test_resolve_or_create_identity_reuses_existing(self, provider: AccountManager) -> None:
        a1 = provider.resolve_or_create_identity("discord", "999", display_name="First")
        a2 = provider.resolve_or_create_identity("discord", "999", display_name="Second")
        assert a1.account_id == a2.account_id

    def test_link_identity(self, provider: AccountManager) -> None:
        account = provider.register("u1")
        assert provider.link_identity(account.account_id, "discord", "555", display_name="User")
        assert provider.get_account_by_identity("discord", "555") is not None

    def test_link_identity_conflict_ignored(self, provider: AccountManager) -> None:
        a1 = provider.resolve_or_create_identity("discord", "111", display_name="u1")
        a2 = provider.register("u2")
        assert not provider.link_identity(a2.account_id, "discord", "111")
        found = provider.get_account_by_identity("discord", "111")
        assert found is not None
        assert found.account_id == a1.account_id


class TestResolve:
    def test_resolve_existing(self, provider: AccountManager) -> None:
        a = provider.register("test")
        found = provider.resolve(a.account_id)
        assert found is not None
        assert found.nickname == "test"

    def test_resolve_nickname_unknown_returns_id(self, provider: AccountManager) -> None:
        assert provider.resolve_nickname("unknown") == "unknown"


class TestUpdate:
    def test_update_nickname(self, provider: AccountManager) -> None:
        a = provider.register("old")
        provider.update_nickname(a.account_id, "new")
        assert provider.resolve_nickname(a.account_id) == "new"

    def test_update_profile(self, provider: AccountManager) -> None:
        a = provider.register("u1")
        provider.update_profile(a.account_id, lang="ja", theme="dark")
        found = provider.resolve(a.account_id)
        assert found is not None
        assert found.profile == {"lang": "ja", "theme": "dark"}
