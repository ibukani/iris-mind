# Iris Account システム

**脳科学対応**: なし（社会的認知基盤）

## 概要

Account システムはユーザーの永続的識別・外部ID連携・セッション紐付けを管理する。
旧 UserStore（user_id ↔ nickname のみ）を置き換え、以下の機能を提供する。

- アカウント CRUD（nickname, profile）
- 外部ID（provider + subject）とのマッピング
- セッション ↔ アカウントの紐付け
- EventBus による状態変化通知

## ディレクトリ構成

```
iris/account/
├── __init__.py       AccountPlugin (STORE phase)
├── models.py         Account, AccountIdentity, SessionBinding
├── store.py          AccountStore (JSONL永続化)
├── provider.py       AccountProvider (コアサービス)
├── events.py         AccountCreated/Updated/IdentityLinked/Presence/SessionBound/Unbound
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
    created_at: str          # ISO 8601 (自動設定)
    last_seen: str | None    # 最終アクティブ時刻
    profile: dict            # 拡張プロフィール（lang, theme等）
```

### AccountIdentity

```python
@dataclass
class AccountIdentity:
    provider: str            # discord / local / web
    subject: str             # provider内の安定ID
    account_id: str          # 紐付けアカウントID
    display_name: str        # provider側表示名
    linked_at: str           # 紐付け時刻
    last_seen: str | None    # 最終検出時刻
    metadata: dict           # guild_id / channel_id等
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
| `register(nickname)` | 新規アカウント作成 |
| `resolve(account_id)` | IDからアカウント取得 |
| `resolve_nickname(account_id)` | ニックネーム取得（未発見時はID返却） |
| `get_account_by_identity(provider, subject)` | 外部IDからアカウント取得 |
| `resolve_or_create_identity(provider, subject, display_name="", metadata=None)` | 外部IDから解決、なければ作成 |
| `link_identity(account_id, provider, subject, display_name="", metadata=None)` | 外部ID紐付け |
| `update_nickname(account_id, nickname)` | ニックネーム更新 |
| `update_profile(account_id, **fields)` | プロフィール更新 |
| `bind_session(session_id, account_id)` | セッション紐付け |
| `unbind_session(session_id)` | セッション解除 → account_id返却 |
| `get_account_by_session(session_id)` | セッションからアカウント取得 |
| `get_active_accounts()` | アクティブアカウント一覧 |
| `get_identities(account_id)` | アカウントに紐づく外部ID一覧 |

## 永続化

| ファイル | 内容 |
|---------|------|
| `.iris/data/accounts.jsonl` | アカウント情報 |
| `.iris/data/account_identities.jsonl` | 外部ID紐付け情報 |
| `.iris/data/account_bindings.jsonl` | セッション紐付け情報 |

## システムメッセージ

`_AccountEventHandler` は `SystemMessageEvent` を処理し、以下のアクションに対応する:

| アクション | 処理 |
|-----------|------|
| `account.identify` | identity解決/作成 + セッション紐付け |
| `account.leave` | セッション解除 |
| `account.get` | 現セッションのアカウント情報取得 |
| `account.update` | ニックネーム・プロフィール更新 |
| `account.link_identity` | 外部ID追加紐付け |

通常チャットでは `Message.speaker` から自動的に `resolve_or_create_identity()` が実行される。Discordグループチャットでは明示的な `account.identify` は任意。

## Presence通知

`bind_session()` / `unbind_session()` は `AccountPresenceEvent` を発行する。IO層はこのEventBusイベントを購読し、接続中のクライアントへ `SystemMessage` を配信する。

| state | SystemMessage action |
|-------|----------------------|
| `entered` | `presence.entered` |
| `left` | `presence.left` |

通知には `account_id`, `nickname`, `identity.provider`, `identity.subject` が含まれる。

## 設定 (config.yaml)

```yaml
account:
    accounts_path: .iris/data/accounts.jsonl
    identities_path: .iris/data/account_identities.jsonl
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
