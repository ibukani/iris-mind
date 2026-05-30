from __future__ import annotations

from pathlib import Path
import threading

from loguru import logger
import orjson

from iris.account.models import Account, AccountIdentity


class AccountStore:
    """アカウントの永続化。

    - accounts.jsonl: アカウント情報
    - identities.jsonl: 外部ID紐付け情報
    """

    def __init__(
        self,
        accounts_path: str = ".iris/data/accounts.jsonl",
        identities_path: str = ".iris/data/account_identities.jsonl",
    ) -> None:
        self._accounts_path = Path(accounts_path)
        self._identities_path = Path(identities_path)
        self._lock = threading.Lock()
        self._accounts_cache: list[dict] | None = None
        self._identities_cache: list[dict] | None = None

    def load_accounts(self) -> list[Account]:
        raw = self._load_jsonl(self._accounts_path, "_accounts_cache")
        return [Account.from_dict(e) for e in raw]

    def load_identities(self) -> list[AccountIdentity]:
        raw = self._load_jsonl(self._identities_path, "_identities_cache")
        return [AccountIdentity.from_dict(e) for e in raw]

    def save_accounts(self, accounts: list[Account]) -> None:
        self._write_jsonl(self._accounts_path, [a.to_dict() for a in accounts], "_accounts_cache")

    def save_identities(self, identities: list[AccountIdentity]) -> None:
        self._write_jsonl(self._identities_path, [i.to_dict() for i in identities], "_identities_cache")

    def add_account(self, account: Account) -> None:
        with self._lock:
            accounts = self.load_accounts()
            accounts.append(account)
            self.save_accounts(accounts)
            logger.info("AccountStore: added account_id={} nickname={}", account.account_id, account.nickname)

    def update_account(self, account: Account) -> None:
        with self._lock:
            accounts = self.load_accounts()
            for i, a in enumerate(accounts):
                if a.account_id == account.account_id:
                    accounts[i] = account
                    break
            self.save_accounts(accounts)

    def add_identity(self, identity: AccountIdentity) -> None:
        with self._lock:
            identities = self.load_identities()
            identities.append(identity)
            self.save_identities(identities)
            logger.info(
                "AccountStore: linked identity provider={} subject={} account={}",
                identity.provider,
                identity.subject,
                identity.account_id,
            )

    def update_identity(self, identity: AccountIdentity) -> None:
        with self._lock:
            identities = self.load_identities()
            for i, current in enumerate(identities):
                if current.provider == identity.provider and current.subject == identity.subject:
                    identities[i] = identity
                    break
            self.save_identities(identities)

    def find_account_by_id(self, account_id: str) -> Account | None:
        for a in self.load_accounts():
            if a.account_id == account_id:
                return a
        return None

    def find_identity(self, provider: str, subject: str) -> AccountIdentity | None:
        for identity in self.load_identities():
            if identity.provider == provider and identity.subject == subject:
                return identity
        return None

    def find_identities_by_account(self, account_id: str) -> list[AccountIdentity]:
        return [i for i in self.load_identities() if i.account_id == account_id]

    def _load_jsonl(self, path: Path, cache_attr: str) -> list[dict[str, object]]:
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        if not path.exists():
            setattr(self, cache_attr, [])
            return []
        entries: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                raw = orjson.loads(line.encode("utf-8"))
                if isinstance(raw, dict):
                    entries.append(raw)
            except orjson.JSONDecodeError:
                logger.warning("AccountStore: skipping corrupt entry: {:.80}", line)
        setattr(self, cache_attr, entries)
        return entries

    def _write_jsonl(self, path: Path, entries: list[dict], cache_attr: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            "\n".join(orjson.dumps(e).decode("utf-8") for e in entries),
            encoding="utf-8",
        )
        tmp.replace(path)
        setattr(self, cache_attr, None)
