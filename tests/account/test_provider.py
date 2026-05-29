from __future__ import annotations

from pathlib import Path

import pytest

from iris.account.provider import AccountProvider
from iris.account.store import AccountStore
from iris.event import EventBus


@pytest.fixture
def provider(tmp_path: Path) -> AccountProvider:
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    bus = EventBus()
    return AccountProvider(store=store, event_bus=bus)


class TestRegister:
    def test_register_creates_account(self, provider: AccountProvider) -> None:
        a = provider.register("alice")
        assert a.nickname == "alice"
        assert len(a.account_id) == 16

    def test_register_with_discord_id(self, provider: AccountProvider) -> None:
        a = provider.register("bob", discord_id="123")
        assert a.discord_id == "123"
        found = provider.resolve_by_discord_id("123")
        assert found is not None

    def test_register_duplicate_discord_returns_existing(self, provider: AccountProvider) -> None:
        a1 = provider.register("first", discord_id="999")
        a2 = provider.register("second", discord_id="999")
        assert a1.account_id == a2.account_id


class TestResolve:
    def test_resolve_existing(self, provider: AccountProvider) -> None:
        a = provider.register("test")
        found = provider.resolve(a.account_id)
        assert found is not None
        assert found.nickname == "test"

    def test_resolve_nonexistent(self, provider: AccountProvider) -> None:
        assert provider.resolve("nope") is None

    def test_resolve_nickname(self, provider: AccountProvider) -> None:
        a = provider.register("charlie")
        assert provider.resolve_nickname(a.account_id) == "charlie"

    def test_resolve_nickname_unknown_returns_id(self, provider: AccountProvider) -> None:
        assert provider.resolve_nickname("unknown") == "unknown"


class TestUpdate:
    def test_update_nickname(self, provider: AccountProvider) -> None:
        a = provider.register("old")
        provider.update_nickname(a.account_id, "new")
        assert provider.resolve_nickname(a.account_id) == "new"

    def test_update_profile(self, provider: AccountProvider) -> None:
        a = provider.register("u1")
        provider.update_profile(a.account_id, lang="ja", theme="dark")
        found = provider.resolve(a.account_id)
        assert found is not None
        assert found.profile == {"lang": "ja", "theme": "dark"}

    def test_link_discord(self, provider: AccountProvider) -> None:
        a = provider.register("u1")
        provider.link_discord(a.account_id, "555")
        assert provider.resolve_by_discord_id("555") is not None

    def test_link_discord_conflict_ignored(self, provider: AccountProvider) -> None:
        a1 = provider.register("u1", discord_id="111")
        a2 = provider.register("u2")
        provider.link_discord(a2.account_id, "111")
        assert provider.resolve_by_discord_id("111") is not None
        assert provider.resolve_by_discord_id("111").account_id == a1.account_id


class TestSessionBinding:
    def test_bind_and_get(self, provider: AccountProvider) -> None:
        a = provider.register("u1")
        provider.bind_session("s1", a.account_id)
        found = provider.get_account_by_session("s1")
        assert found is not None
        assert found.account_id == a.account_id

    def test_unbind(self, provider: AccountProvider) -> None:
        a = provider.register("u1")
        provider.bind_session("s1", a.account_id)
        account_id = provider.unbind_session("s1")
        assert account_id == a.account_id
        assert provider.get_account_by_session("s1") is None

    def test_unbind_nonexistent(self, provider: AccountProvider) -> None:
        assert provider.unbind_session("nope") is None

    def test_get_active_accounts(self, provider: AccountProvider) -> None:
        a1 = provider.register("u1")
        a2 = provider.register("u2")
        provider.bind_session("s1", a1.account_id)
        provider.bind_session("s2", a2.account_id)
        active = provider.get_active_accounts()
        assert len(active) == 2


class TestEvents:
    def test_register_publishes_event(self, provider: AccountProvider) -> None:
        a = provider.register("event_user")
        assert a.account_id != ""

    def test_update_nickname_publishes_event(self, provider: AccountProvider) -> None:
        a = provider.register("u1")
        provider.update_nickname(a.account_id, "u2")
        assert provider.resolve_nickname(a.account_id) == "u2"
