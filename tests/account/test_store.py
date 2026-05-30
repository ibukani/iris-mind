from __future__ import annotations

from pathlib import Path

import pytest

from iris.account.models import Account, AccountIdentity
from iris.account.store import AccountStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> AccountStore:
    return AccountStore(
        accounts_path=str(tmp_path / "accounts.jsonl"),
        identities_path=str(tmp_path / "identities.jsonl"),
    )


class TestAccountStore:
    def test_add_and_find_by_id(self, tmp_store: AccountStore) -> None:
        a = Account(display_name="alice")
        tmp_store.add_account(a)
        found = tmp_store.find_account_by_id(a.account_id)
        assert found is not None
        assert found.display_name == "alice"

    def test_update_account(self, tmp_store: AccountStore) -> None:
        a = Account(display_name="old")
        tmp_store.add_account(a)
        a.display_name = "new"
        tmp_store.update_account(a)
        found = tmp_store.find_account_by_id(a.account_id)
        assert found is not None
        assert found.display_name == "new"

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
