from __future__ import annotations

from pathlib import Path

import pytest

from iris.account.handler import _AccountEventHandler
from iris.account.provider import AccountProvider
from iris.account.store import AccountStore
from iris.event.event_types import SystemMessageEvent


@pytest.fixture
def handler_and_provider(tmp_path: Path) -> tuple[_AccountEventHandler, AccountProvider]:
    store = AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    provider = AccountProvider(store=store)
    return _AccountEventHandler(account_provider=provider), provider


def _msg(action: str, **kwargs: object) -> SystemMessageEvent:
    return SystemMessageEvent(timestamp=None, source="test", action=action, **kwargs)


class TestIdentify:
    def test_identify_creates_account_and_binds_session(
        self,
        handler_and_provider: tuple[_AccountEventHandler, AccountProvider],
    ) -> None:
        h, p = handler_and_provider
        result = h.handle_system_message(
            _msg(
                "account.identify",
                identity={"provider": "discord", "subject": "123", "display_name": "Alice"},
            ),
            "s1",
        )
        assert result is not None
        assert result.action == "account.identify"
        assert result.account_id != ""
        assert result.nickname == "Alice"
        assert p.get_account_by_session("s1") is not None

    def test_identify_requires_identity(
        self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]
    ) -> None:
        h, _ = handler_and_provider
        result = h.handle_system_message(_msg("account.identify"), "s1")
        assert result is not None
        assert "Error" in (result.text or "")


class TestGet:
    def test_get_current_account(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        account = p.resolve_or_create_identity("discord", "123", display_name="Alice")
        p.bind_session("s1", account.account_id)
        result = h.handle_system_message(_msg("account.get"), "s1")
        assert result is not None
        assert result.account_id == account.account_id
        assert "identities" in (result.text or "")


class TestUpdate:
    def test_update_nickname_and_profile(
        self,
        handler_and_provider: tuple[_AccountEventHandler, AccountProvider],
    ) -> None:
        h, p = handler_and_provider
        account = p.register("old")
        p.bind_session("s1", account.account_id)
        result = h.handle_system_message(_msg("account.update", nickname="new", profile={"lang": "ja"}), "s1")
        assert result is not None
        assert result.nickname == "new"
        updated = p.resolve(account.account_id)
        assert updated is not None
        assert updated.nickname == "new"
        assert updated.profile == {"lang": "ja"}


class TestLinkIdentity:
    def test_link_identity(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        account = p.register("u1")
        p.bind_session("s1", account.account_id)
        result = h.handle_system_message(
            _msg(
                "account.link_identity",
                identity={"provider": "local", "subject": "local-user", "display_name": "Local"},
            ),
            "s1",
        )
        assert result is not None
        assert "local:local-user" in (result.text or "")
        assert p.get_account_by_identity("local", "local-user") is not None


class TestLeave:
    def test_leave_unbinds_session(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        account = p.register("u1")
        p.bind_session("s1", account.account_id)
        result = h.handle_system_message(_msg("account.leave"), "s1")
        assert result is not None
        assert result.action == "account.leave"
        assert p.get_account_by_session("s1") is None
