from __future__ import annotations

from pathlib import Path

import pytest

from iris.account.models import Account, AccountIdentity, SessionBinding
from iris.account.store import AccountStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> AccountStore:
    return AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
        bindings_path=str(tmp_path / "bindings.jsonl"),
    )


class TestAccountStore:
    def test_add_and_find_by_id(self, tmp_store: AccountStore) -> None:
        a = Account(nickname="alice")
        tmp_store.add_account(a)
        found = tmp_store.find_account_by_id(a.account_id)
        assert found is not None
        assert found.nickname == "alice"

    def test_update_account(self, tmp_store: AccountStore) -> None:
        a = Account(nickname="old")
        tmp_store.add_account(a)
        a.nickname = "new"
        tmp_store.update_account(a)
        found = tmp_store.find_account_by_id(a.account_id)
        assert found is not None
        assert found.nickname == "new"

    def test_load_accounts_empty(self, tmp_store: AccountStore) -> None:
        assert tmp_store.load_accounts() == []


class TestIdentityStore:
    def test_add_and_find_identity(self, tmp_store: AccountStore) -> None:
        identity = AccountIdentity(provider="discord", subject="999", account_id="a1")
        tmp_store.add_identity(identity)
        found = tmp_store.find_identity("discord", "999")
        assert found is not None
        assert found.account_id == "a1"

    def test_find_identities_by_account(self, tmp_store: AccountStore) -> None:
        tmp_store.add_identity(AccountIdentity(provider="discord", subject="1", account_id="a1"))
        tmp_store.add_identity(AccountIdentity(provider="local", subject="2", account_id="a1"))
        assert len(tmp_store.find_identities_by_account("a1")) == 2

    def test_find_nonexistent_returns_none(self, tmp_store: AccountStore) -> None:
        assert tmp_store.find_account_by_id("nope") is None
        assert tmp_store.find_identity("discord", "nope") is None


class TestBindingStore:
    def test_add_and_find_active(self, tmp_store: AccountStore) -> None:
        b = SessionBinding(session_id="s1", account_id="a1")
        tmp_store.add_binding(b)
        found = tmp_store.find_active_binding("s1")
        assert found is not None
        assert found.account_id == "a1"

    def test_update_binding_disconnect(self, tmp_store: AccountStore) -> None:
        b = SessionBinding(session_id="s1", account_id="a1")
        tmp_store.add_binding(b)
        b.disconnected_at = "2025-01-01T00:00:00"
        tmp_store.update_binding(b)
        assert tmp_store.find_active_binding("s1") is None

    def test_find_bindings_by_account(self, tmp_store: AccountStore) -> None:
        tmp_store.add_binding(SessionBinding(session_id="s1", account_id="a1"))
        tmp_store.add_binding(SessionBinding(session_id="s2", account_id="a1"))
        tmp_store.add_binding(SessionBinding(session_id="s3", account_id="a2"))
        bindings = tmp_store.find_bindings_by_account("a1")
        assert len(bindings) == 2
