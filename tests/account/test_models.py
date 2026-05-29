from __future__ import annotations

from iris.account.models import Account, SessionBinding


class TestAccountModel:
    def test_auto_generate_id(self) -> None:
        a = Account(nickname="test")
        assert len(a.account_id) == 16
        assert a.nickname == "test"

    def test_auto_created_at(self) -> None:
        a = Account(nickname="x")
        assert a.created_at != ""

    def test_to_dict_roundtrip(self) -> None:
        a = Account(nickname="alice", discord_id="12345", profile={"lang": "ja"})
        d = a.to_dict()
        b = Account.from_dict(d)
        assert b.account_id == a.account_id
        assert b.nickname == "alice"
        assert b.discord_id == "12345"
        assert b.profile == {"lang": "ja"}

    def test_from_dict_none_discord_id(self) -> None:
        b = Account.from_dict({"account_id": "x", "nickname": "y", "discord_id": None})
        assert b.discord_id is None


class TestSessionBinding:
    def test_auto_connected_at(self) -> None:
        b = SessionBinding(session_id="s1", account_id="a1")
        assert b.connected_at != ""
        assert b.disconnected_at is None

    def test_to_dict_roundtrip(self) -> None:
        b = SessionBinding(session_id="s1", account_id="a1", disconnected_at="2025-01-01T00:00:00")
        d = b.to_dict()
        c = SessionBinding.from_dict(d)
        assert c.session_id == "s1"
        assert c.account_id == "a1"
        assert c.disconnected_at == "2025-01-01T00:00:00"
