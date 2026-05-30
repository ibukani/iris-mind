# Iris Account システム

## 概要

Account システムはユーザーの永続的識別・外部ID連携を管理する。
旧 UserStore（user_id ↔ nickname のみ）を置き換え、以下の機能を提供する。

- アカウント CRUD（nickname, profile）
- 外部ID（provider + subject）とのマッピング
- EventBus による状態変化通知

**Account 層はルーム管理を行わない。** セッション/ルーム紐付けは Room 層（`iris/room/`）が担当する。

## ディレクトリ構成

```
iris/account/
├── __init__.py       AccountPlugin (STORE phase)
├── models.py         Account, AccountIdentity
├── store.py          AccountStore (JSONL永続化)
├── provider.py       AccountProvider (コアサービス)
├── events.py         AccountCreated/Updated/IdentityLinked
├── handler.py        _AccountEventHandler (account.* ControlMessage処理)
└── hooks.py          EventBus Hook登録
```

## プラグイン情報

| 項目 | 値 |
|------|-----|
| name | `account` |
| category | `LAYER` |
| phase | `STORE(15)` |
| provides | `AccountProvider`, `AccountStore`, `_AccountEventHandler` |
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

## AccountProvider API

| メソッド | 説明 |
|---------|------|
| `register(nickname)` | 新規アカウント作成 |
| `resolve(account_id)` | IDからアカウント取得 |
| `get_account_by_identity(provider, subject)` | 外部IDからアカウント取得 |
| `resolve_or_create_identity(provider, subject, display_name="", metadata=None)` | 外部IDから解決、なければ作成 |
| `link_identity(account_id, provider, subject, display_name="", metadata=None)` | 外部ID紐付け |
| `update_nickname(account_id, nickname)` | ニックネーム更新 |
| `update_profile(account_id, **fields)` | プロフィール更新 |
| `get_identities(account_id)` | アカウントに紐づく外部ID一覧 |

## 永続化

| ファイル | 内容 |
|---------|------|
| `.iris/data/accounts.jsonl` | アカウント情報 |
| `.iris/data/account_identities.jsonl` | 外部ID紐付け情報 |

## ControlMessage

`_AccountEventHandler` は `ControlMessageEvent` を処理し、以下のアクションに対応する:

| アクション | 処理 | 備考 |
|-----------|------|------|
| `account.identify` | identity解決/作成、アカウント情報返却 | 旧 `account.join` |
| `account.profile` | 現セッションのアカウント情報取得 | 旧 `account.get` |
| `account.update` | ニックネーム・プロフィール更新 | 同左 |
| `account.link` | 外部ID追加紐付け | 旧 `account.link_identity` |

通常チャットでは `Message.speaker` から自動的に `resolve_or_create_identity()` が実行される。
Discordグループチャットでは明示的な `account.identify` は任意。

**Room 参加/退室は `room.join` / `room.leave` を使用する。**

## Presence通知

`RoomJoinedEvent` / `RoomLeftEvent` は Room 層から発行される。IO層（`iris/io/handler.py`）がこれらの EventBus イベントを購読し、接続中のクライアントへ `ControlMessage` を配信する。

| EventBus イベント | ControlMessage action |
|------------------|----------------------|
| `RoomJoinedEvent` | `presence.joined` |
| `RoomLeftEvent` | `presence.left` |

## 設定 (config.yaml)

```yaml
account:
    accounts_path: .iris/data/accounts.jsonl
    identities_path: .iris/data/account_identities.jsonl
```

## 依存関係

```
Account層 ──→ EventBus
Room層    ──→ AccountProvider (room.join時のaccount作成フォールバック)
Kernel層  ──→ AccountHandler (account.* ルーティング)
Memory層  ──→ AccountHandler (identify_message_speaker呼出)
IO層      ──→ EventBus (RoomJoinedEvent/RoomLeftEvent購読 → presence通知)
```

## テスト

```powershell
uv run pytest tests/account/ -v
```
