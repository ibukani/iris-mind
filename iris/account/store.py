from __future__ import annotations

from pathlib import Path
import threading

from loguru import logger
import orjson

from iris.account.models import Account, SessionBinding


class AccountStore:
    """アカウント・セッション紐付けの永続化。

    - accounts.jsonl: アカウント情報
    - bindings.jsonl: セッション紐付け情報
    """

    def __init__(
        self,
        accounts_path: str = ".iris/data/accounts.jsonl",
        bindings_path: str = ".iris/data/account_bindings.jsonl",
    ) -> None:
        self._accounts_path = Path(accounts_path)
        self._bindings_path = Path(bindings_path)
        self._lock = threading.Lock()
        self._accounts_cache: list[dict] | None = None
        self._bindings_cache: list[dict] | None = None

    def load_accounts(self) -> list[Account]:
        raw = self._load_jsonl(self._accounts_path, "_accounts_cache")
        return [Account.from_dict(e) for e in raw]

    def load_bindings(self) -> list[SessionBinding]:
        raw = self._load_jsonl(self._bindings_path, "_bindings_cache")
        return [SessionBinding.from_dict(e) for e in raw]

    def save_accounts(self, accounts: list[Account]) -> None:
        self._write_jsonl(self._accounts_path, [a.to_dict() for a in accounts], "_accounts_cache")

    def save_bindings(self, bindings: list[SessionBinding]) -> None:
        self._write_jsonl(self._bindings_path, [b.to_dict() for b in bindings], "_bindings_cache")

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

    def add_binding(self, binding: SessionBinding) -> None:
        with self._lock:
            bindings = self.load_bindings()
            bindings.append(binding)
            self.save_bindings(bindings)
            logger.debug("AccountStore: bound session={} to account={}", binding.session_id, binding.account_id)

    def update_binding(self, binding: SessionBinding) -> None:
        with self._lock:
            bindings = self.load_bindings()
            for i, b in enumerate(bindings):
                if b.session_id == binding.session_id and b.disconnected_at is None:
                    bindings[i] = binding
                    break
            self.save_bindings(bindings)

    def find_account_by_discord_id(self, discord_id: str) -> Account | None:
        for a in self.load_accounts():
            if a.discord_id == discord_id:
                return a
        return None

    def find_account_by_id(self, account_id: str) -> Account | None:
        for a in self.load_accounts():
            if a.account_id == account_id:
                return a
        return None

    def find_active_binding(self, session_id: str) -> SessionBinding | None:
        for b in self.load_bindings():
            if b.session_id == session_id and b.disconnected_at is None:
                return b
        return None

    def find_bindings_by_account(self, account_id: str) -> list[SessionBinding]:
        return [b for b in self.load_bindings() if b.account_id == account_id]

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
