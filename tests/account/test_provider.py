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
        identities_path=str(tmp_path / "identities.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    return AccountProvider(store=store, event_bus=EventBus())


@pytest.fixture
def provider_and_bus(tmp_path: Path) -> tuple[AccountProvider, EventBus]:
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    bus = EventBus()
    return AccountProvider(store=store, event_bus=bus), bus


class TestRegister:
    def test_register_creates_account(self, provider: AccountProvider) -> None:
        a = provider.register("alice")
        assert a.nickname == "alice"
        assert len(a.account_id) == 16


class TestIdentity:
    def test_resolve_or_create_identity_creates_account(self, provider: AccountProvider) -> None:
        account = provider.resolve_or_create_identity("discord", "123", display_name="Bob")
        assert account.nickname == "Bob"
        found = provider.get_account_by_identity("discord", "123")
        assert found is not None
        assert found.account_id == account.account_id

    def test_resolve_or_create_identity_reuses_existing(self, provider: AccountProvider) -> None:
        a1 = provider.resolve_or_create_identity("discord", "999", display_name="First")
        a2 = provider.resolve_or_create_identity("discord", "999", display_name="Second")
        assert a1.account_id == a2.account_id

    def test_link_identity(self, provider: AccountProvider) -> None:
        account = provider.register("u1")
        assert provider.link_identity(account.account_id, "discord", "555", display_name="User")
        assert provider.get_account_by_identity("discord", "555") is not None

    def test_link_identity_conflict_ignored(self, provider: AccountProvider) -> None:
        a1 = provider.resolve_or_create_identity("discord", "111", display_name="u1")
        a2 = provider.register("u2")
        assert not provider.link_identity(a2.account_id, "discord", "111")
        found = provider.get_account_by_identity("discord", "111")
        assert found is not None
        assert found.account_id == a1.account_id


class TestResolve:
    def test_resolve_existing(self, provider: AccountProvider) -> None:
        a = provider.register("test")
        found = provider.resolve(a.account_id)
        assert found is not None
        assert found.nickname == "test"

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

    def test_get_active_accounts(self, provider: AccountProvider) -> None:
        a1 = provider.register("u1")
        a2 = provider.register("u2")
        provider.bind_session("s1", a1.account_id)
        provider.bind_session("s2", a2.account_id)
        assert len(provider.get_active_accounts()) == 2

    def test_multiple_rooms_on_same_session(self, provider: AccountProvider) -> None:
        a1 = provider.register("u1")
        a2 = provider.register("u2")
        provider.bind_session("s1", a1.account_id, room_id="room-a")
        provider.bind_session("s1", a2.account_id, room_id="room-b")

        found_a = provider.get_account_by_session("s1", "room-a")
        found_b = provider.get_account_by_session("s1", "room-b")

        assert found_a is not None
        assert found_a.account_id == a1.account_id
        assert found_b is not None
        assert found_b.account_id == a2.account_id

    def test_unbind_all_for_session_unbinds_all_rooms(self, provider: AccountProvider) -> None:
        a1 = provider.register("u1")
        a2 = provider.register("u2")
        provider.bind_session("s1", a1.account_id, room_id="room-a")
        provider.bind_session("s1", a2.account_id, room_id="room-b")

        account_ids = provider.unbind_all_for_session("s1")

        assert set(account_ids) == {a1.account_id, a2.account_id}
        assert provider.get_account_by_session("s1", "room-a") is None
        assert provider.get_account_by_session("s1", "room-b") is None

    def test_presence_event_includes_identity(
        self,
        provider_and_bus: tuple[AccountProvider, EventBus],
    ) -> None:
        provider, bus = provider_and_bus
        events = []
        bus.subscribe("AccountPresenceEvent", lambda ev: events.append(ev))
        account = provider.resolve_or_create_identity("discord", "123", display_name="u1")
        provider.bind_session("s1", account.account_id, room_id="room-a")

        assert events[-1].provider == "discord"
        assert events[-1].subject == "123"
        assert events[-1].room_id == "room-a"
