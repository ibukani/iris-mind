# Iris Account システム

**脳科学対応**: なし（社会的認知基盤）

## 概要

Account システムはユーザーの永続的識別・外部ID連携・セッション紐付けを管理する。
旧 UserStore（user_id ↔ nickname のみ）を置き換え、以下の機能を提供する。

- アカウント CRUD（nickname, discord_id, profile）
- 外部ID（discord_id）とのマッピング
- セッション ↔ アカウントの紐付け
- EventBus による状態変化通知

## ディレクトリ構成

```
iris/account/
├── __init__.py       AccountPlugin (STORE phase)
├── models.py         Account, SessionBinding
├── store.py          AccountStore (JSONL永続化)
├── provider.py       AccountProvider (コアサービス)
├── events.py         AccountCreated/Updated/SessionBound/Unbound
├── handler.py        _AccountEventHandler (SystemMessage処理)
└── hooks.py          EventBus Hook登録
```

## プラグイン情報

| 項目 | 値 |
|------|-----|
| name | `account` |
| category | `LAYER` |
| phase | `STORE(15)` |
| provides | `AccountProvider`, `AccountStore` |
| dependencies | `EventBus` |

## モデル

### Account

```python
@dataclass
class Account:
    account_id: str          # UUID hex[:16] (自動生成)
    nickname: str            # 表示名
    discord_id: str | None   # Discord user ID
    created_at: str          # ISO 8601 (自動設定)
    last_seen: str | None    # 最終アクティブ時刻
    profile: dict            # 拡張プロフィール（lang, theme等）
```

### SessionBinding

```python
@dataclass
class SessionBinding:
    session_id: str          # セッションUUID
    account_id: str          # 紐付けアカウントID
    connected_at: str        # 接続時刻 (ISO 8601)
    disconnected_at: str | None  # 切断時刻
```

## AccountProvider API

| メソッド | 説明 |
|---------|------|
| `register(nickname, discord_id=None)` | 新規作成。discord_id重複時は既存返却 |
| `resolve(account_id)` | IDからアカウント取得 |
| `resolve_by_discord_id(discord_id)` | Discord IDから取得 |
| `resolve_nickname(account_id)` | ニックネーム取得（未発見時はID返却） |
| `update_nickname(account_id, nickname)` | ニックネーム更新 |
| `update_profile(account_id, **fields)` | プロフィール更新 |
| `link_discord(account_id, discord_id)` | Discord ID紐付け |
| `bind_session(session_id, account_id)` | セッション紐付け |
| `unbind_session(session_id)` | セッション解除 → account_id返却 |
| `get_account_by_session(session_id)` | セッションからアカウント取得 |
| `get_active_accounts()` | アクティブアカウント一覧 |

## 永続化

| ファイル | 内容 |
|---------|------|
| `.iris/data/accounts.jsonl` | アカウント情報 |
| `.iris/data/account_bindings.jsonl` | セッション紐付け情報 |

## システムメッセージ

`_AccountEventHandler` は `SystemMessageEvent` を処理し、以下のアクションに対応する:

| アクション | 処理 |
|-----------|------|
| `user_register` | アカウント作成 + セッション紐付け |
| `user_entered` | セッション紐付け + last_seen更新 |
| `user_left` | セッション解除 |
| `nickname_update` | ニックネーム変更 |
| `account.get_id` | 自分のアカウントID確認 |
| `account.get_profile` | プロフィール取得 |
| `account.link` | Discord ID紐付け |

## 設定 (config.yaml)

```yaml
account:
    accounts_path: .iris/data/accounts.jsonl
    bindings_path: .iris/data/account_bindings.jsonl
```

## 依存関係

```
Memory層 ──→ AccountProvider (SystemMessage処理)
Agency層 ──→ AccountProvider (ニックネーム解決)
IO層    ──→ EventBus (SystemMessageEvent発行)
Kernel層 ──→ EventBus (SystemMessage変換)
```

## テスト

```powershell
uv run pytest tests/account/ -v
```
