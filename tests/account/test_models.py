from __future__ import annotations

from iris.account.models import Account, AccountIdentity, SessionBinding


class TestAccountModel:
    def test_auto_generate_id(self) -> None:
        a = Account(nickname="test")
        assert len(a.account_id) == 16
        assert a.nickname == "test"

    def test_to_dict_roundtrip(self) -> None:
        a = Account(nickname="alice", profile={"lang": "ja"})
        d = a.to_dict()
        b = Account.from_dict(d)
        assert b.account_id == a.account_id
        assert b.nickname == "alice"
        assert b.profile == {"lang": "ja"}


class TestAccountIdentity:
    def test_to_dict_roundtrip(self) -> None:
        identity = AccountIdentity(
            provider="discord",
            subject="12345",
            account_id="a1",
            display_name="Alice",
            metadata={"guild_id": "g1"},
        )
        restored = AccountIdentity.from_dict(identity.to_dict())
        assert restored.provider == "discord"
        assert restored.subject == "12345"
        assert restored.account_id == "a1"
        assert restored.display_name == "Alice"
        assert restored.metadata == {"guild_id": "g1"}


class TestSessionBinding:
    def test_auto_connected_at(self) -> None:
        b = SessionBinding(session_id="s1", account_id="a1")
        assert b.connected_at != ""
        assert b.disconnected_at is None

    def test_to_dict_roundtrip(self) -> None:
        b = SessionBinding(session_id="s1", account_id="a1", disconnected_at="2025-01-01T00:00:00")
        c = SessionBinding.from_dict(b.to_dict())
        assert c.session_id == "s1"
        assert c.account_id == "a1"
        assert c.disconnected_at == "2025-01-01T00:00:00"
