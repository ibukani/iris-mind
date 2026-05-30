# アカウント管理システム (ACCOUNT)

## 責務

- ユーザーアカウントのCRUD
- 外部ID（provider + subject）とのマッピング
- ControlMessage によるアカウント操作ルーティング

## ファイル構成

```
iris/account/
├── __init__.py       AccountPlugin (STORE phase)
├── models.py         Account, AccountIdentity
├── store.py          AccountStore (JSONL永続化)
├── manager.py        AccountManager (コアサービス)
├── dispatcher.py     _AccountDispatcher (ControlMessage処理)
├── events.py         AccountCreated/Updated/IdentityLinked/Presence
└── hooks.py          EventBus Hook登録
```

## プラグイン情報

| 項目 | 値 |
|------|-----|
| name | `account` |
| category | `LAYER` |
| phase | `STORE(15)` |
| provides | `AccountManager`, `AccountStore`, `_AccountDispatcher` |
| dependencies | `EventBus` |

## モデル

### Account

```python
@dataclass
class Account:
    account_id: str          # UUID hex[:16] (自動生成)
    display_name: str        # 表示名
    created_at: str          # ISO 8601 (自動設定)
    last_seen: str | None    # 最終アクセス
    profile: dict            # プロフィール情報 (自由形式)
```

### AccountIdentity

```python
@dataclass
class AccountIdentity:
    provider: str            # discord / local / web
    subject: str             # provider内の安定ID
    account_id: str          # 紐付くアカウント
    provider_name: str       # provider側表示名
    linked_at: str           # 紐付け日時
    last_seen: str | None    # 最終アクセス
    metadata: dict           # 追加情報
```

## AccountManager API

| メソッド | 説明 |
|----------|------|
| `register(display_name)` | 新規アカウント作成 |
| `resolve(account_id)` | account_id からアカウント取得 |
| `resolve_display_name(account_id)` | account_id から表示名取得 |
| `get_account_by_identity(provider, subject)` | 外部IDからアカウント取得 |
| `resolve_or_create_identity(provider, subject, provider_name="", metadata=None)` | 外部IDから解決、なければ作成 |
| `link_identity(account_id, provider, subject, provider_name="", metadata=None)` | 外部ID紐付け |
| `update_display_name(account_id, display_name)` | 表示名更新 |
| `update_last_seen(account_id)` | last_seen 更新 |
| `update_profile(account_id, **fields)` | プロフィール更新 |
| `list_accounts()` | 全アカウント一覧 |
| `get_identities(account_id)` | 紐付いた外部ID一覧 |

## イベント

| イベント | 発行タイミング |
|----------|---------------|
| `AccountCreatedEvent` | アカウント作成時 |
| `AccountUpdatedEvent` | プロフィール/表示名更新時 |
| `AccountIdentityLinkedEvent` | 外部ID紐付け時 |

## ControlMessage 処理

`_AccountDispatcher` は `ControlMessageEvent` を処理し、以下のアクションに対応する:

| アクション | 処理 |
|-----------|------|
| `account.identify` | identity解決 + アカウント作成 |
| `account.profile` | プロフィール取得 |
| `account.update` | 表示名/プロフィール更新 |
| `account.link` | 外部ID紐付け |

## 依存関係

```
Memory層 ──→ AccountDispatcher (identify_message_speaker呼出)
Agency層 ──→ AccountManager (表示名解決)
IO層    ──→ EventBus (ControlMessageEvent発行)
Kernel層 ──→ EventBus (ControlMessage変換)
```

## テスト

```powershell
uv run pytest tests/account/ -v
```
