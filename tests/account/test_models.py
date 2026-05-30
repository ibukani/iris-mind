from __future__ import annotations

from iris.account.models import Account, AccountIdentity


class TestAccountModel:
    def test_auto_generate_id(self) -> None:
        a = Account(display_name="test")
        assert len(a.account_id) == 16
        assert a.display_name == "test"

    def test_to_dict_roundtrip(self) -> None:
        a = Account(display_name="alice", profile={"lang": "ja"})
        d = a.to_dict()
        b = Account.from_dict(d)
        assert b.account_id == a.account_id
        assert b.display_name == "alice"
        assert b.profile == {"lang": "ja"}


class TestAccountIdentity:
    def test_to_dict_roundtrip(self) -> None:
        identity = AccountIdentity(
            provider="discord",
            subject="12345",
            account_id="a1",
            provider_name="Alice",
            metadata={"guild_id": "g1"},
        )
        restored = AccountIdentity.from_dict(identity.to_dict())
        assert restored.provider == "discord"
        assert restored.subject == "12345"
        assert restored.account_id == "a1"
        assert restored.provider_name == "Alice"
        assert restored.metadata == {"guild_id": "g1"}
