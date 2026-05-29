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
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )
    provider = AccountProvider(store=store)
    h = _AccountEventHandler(account_provider=provider)
    return h, provider


def _msg(action: str, **kwargs: object) -> SystemMessageEvent:
    return SystemMessageEvent(timestamp=None, source="test", action=action, **kwargs)


class TestRegister:
    def test_user_register(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, _p = handler_and_provider
        result = h.handle_system_message(_msg("user_register", nickname="alice"), "s1")
        assert result is not None
        assert result.action == "user_register"
        assert result.nickname == "alice"
        assert result.user_id != ""

    def test_user_register_binds_session(
        self,
        handler_and_provider: tuple[_AccountEventHandler, AccountProvider],
    ) -> None:
        h, p = handler_and_provider
        result = h.handle_system_message(_msg("user_register", nickname="bob"), "s1")
        assert result is not None
        account = p.get_account_by_session("s1")
        assert account is not None
        assert account.account_id == result.user_id


class TestEntered:
    def test_user_entered(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("charlie")
        result = h.handle_system_message(_msg("user_entered", user_id=a.account_id), "s1")
        assert result is not None
        assert result.nickname == "charlie"

    def test_user_entered_unknown_id(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, _ = handler_and_provider
        result = h.handle_system_message(_msg("user_entered", user_id="unknown"), "s1")
        assert result is not None
        assert "Error" in (result.text or "")

    def test_user_entered_no_id(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, _ = handler_and_provider
        result = h.handle_system_message(_msg("user_entered"), "s1")
        assert result is not None
        assert "Error" in (result.text or "")


class TestLeft:
    def test_user_left(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("dave")
        p.bind_session("s1", a.account_id)
        result = h.handle_system_message(_msg("user_left", user_id=a.account_id), "s1")
        assert result is not None
        assert result.nickname == "dave"
        assert p.get_account_by_session("s1") is None


class TestNicknameUpdate:
    def test_nickname_update(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("old_name")
        result = h.handle_system_message(_msg("nickname_update", user_id=a.account_id, nickname="new_name"), "s1")
        assert result is not None
        assert result.nickname == "new_name"
        assert p.resolve_nickname(a.account_id) == "new_name"


class TestGetId:
    def test_get_id_logged_in(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("u1")
        p.bind_session("s1", a.account_id)
        result = h.handle_system_message(_msg("account.get_id"), "s1")
        assert result is not None
        assert result.user_id == a.account_id

    def test_get_id_not_logged_in(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, _ = handler_and_provider
        result = h.handle_system_message(_msg("account.get_id"), "s1")
        assert result is not None
        assert "Error" in (result.text or "")


class TestGetProfile:
    def test_get_profile(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("u1")
        p.update_profile(a.account_id, lang="ja")
        p.bind_session("s1", a.account_id)
        result = h.handle_system_message(_msg("account.get_profile"), "s1")
        assert result is not None
        assert "ja" in (result.text or "")


class TestLink:
    def test_link_discord(self, handler_and_provider: tuple[_AccountEventHandler, AccountProvider]) -> None:
        h, p = handler_and_provider
        a = p.register("u1")
        p.bind_session("s1", a.account_id)
        result = h.handle_system_message(_msg("account.link", text="discord_123"), "s1")
        assert result is not None
        assert "discord_123" in (result.text or "")
        assert p.resolve_by_discord_id("discord_123") is not None
