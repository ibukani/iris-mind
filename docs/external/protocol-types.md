# Iris Mind 通信プロトコル データ型定義

> 本ファイルは [`protocol-spec.md`](./protocol-spec.md) から分割されたデータ型定義セクションである。プロトコル全体の概要・通信方式・エラーハンドリングは [`protocol-spec.md`](./protocol-spec.md) を参照。接続シーケンス・実装例は [`protocol-flows.md`](./protocol-flows.md) を参照。

## 1. データ型定義

### 1.1 Permission (メタデータで指定)

認証メタデータの `permissions` キーにコンマ区切りで指定する。

| 値 | 説明 |
|----|------|
| `send_chat` | テキスト入力を送信可能 |
| `receive_chat` | 応答を受信可能 |
| `send_command` | `/` コマンドを送信可能 |
| `receive_command` | コマンド結果を受信可能 |
| `receive_log` | ログ・デバッグ情報を受信可能 |
| `interrupt` | 生成中断を要求可能 |
| `execute_action` | アクション実行要求を受信可能 |
| `send_voice_indicator` | 音声録音状態を送信可能 |

### 1.2 Direction (`Message.direction`)

| 値 | 方向 | 説明 |
|----|------|------|
| `request` | Client→Server | クライアントからのリクエスト |
| `response` | Server→Client | サーバーからの単一応答（最終結果） |
| `stream` | Server→Client | ストリーミング中継（`state` と併用） |
| `event` | Server→Client | イベント通知（ブロードキャスト等） |

### 1.3 msg_type 定義 (`Message.msg_type`)

| msg_type | 通信方向 | 説明 |
|----------|---------|------|
| `chat` | 双方向 | テキスト会話メッセージ（`direction:stream` でストリーミング、`direction:response` で最終応答） |
| `system` | Client→Server | システム制御メッセージ |
| `interrupt` | Client→Server | 生成中断要求 |
| `execute` | Server→Client | アクション実行要求（tools使用時） |
| `execute_result` | Client→Server | アクション実行結果 |
| `proactive` | Server→Client | 自発発話（stream を経ず1メッセージで完了） |
| `ack` | Server→Client | 受信確認（`metadata.ack_required` 時） |
| `error` | Server→Client | エラー通知 |
| `voice_indicator` | Client→Server | 音声録音状態通知（制御信号）。`content` が `"true"` で録音開始、`"false"` で録音終了。`direction:event` で送信 |

### 1.4 Role（`source_role` / `target_role`）

`Message.source_role` と `Message.target_role` は自由文字列。事前定義されたenumは存在せず、セッション配送ラベルとして機能する。

**特殊値:**

| 値 | フィールド | 意味 |
|----|-----------|------|
| `"mind"` | source_role（S→C）, target_role（C→S） | Iris 自身を示す。サーバー送信メッセージの source_role は常に `"mind"` |
| `"*"` | target_role | 全セッションへのブロードキャスト。`target_role` のデフォルト値 |
| `"external"` | source_role（C→S） | クライアント未指定時のデフォルト。認証メタデータの `role` も未指定時は `"external"` |

**注意:**
- クライアントが送信した `Message.source_role` はサーバーが認証済みセッションの role で上書きする。送信元詐称不可。
- `target_role` が空文字の場合はサーバー側で `"*"` にフォールバックする。
- **Iris 自身に発話を届けるには `target_role="mind"` が必須。** 省略または誤った role を指定すると、Iris はメッセージを処理せず応答を返さない（セッション間ルーティングに回る）。
- ルーターは `target_role` が一致するセッションに配送する。`"*"` は全アクティブセッションにブロードキャスト。

### 1.5 メッセージメタデータと補助フィールド

#### 1.5.1 `content_type`

`Message.content_type` は MIME type を示す文字列。

| 値 | 説明 |
|----|------|
| `"text/plain"` | プレーンテキスト（デフォルト。現在唯一使用される値） |

将来 `"text/markdown"` 等が追加される可能性がある。

#### 1.5.2 `metadata` 標準キー

`Message.metadata` は `map<string, string>`。以下の標準キーが定義されている:

| キー | 方向 | 型 | 説明 |
|------|------|-----|------|
| `ack_required` | C→S | `"true"` / `"false"` | 文字列の真偽値。true 時サーバーが確認応答を返送（protocol-flows.md §2.5） |
| `account_id` | S→C | string | 応答メッセージに対応するアカウントID |
| `room_id` | S→C | string | 応答メッセージのルームID |
| `error` | S→C | `"true"` | エラー応答の判別用。値が `"true"` のメッセージはエラー通知。§1.3 の `msg_type="error"` とは異なり、`msg_type="response"` に付与される（§4参照） |

クライアントは任意のキーを追加可能。gRPC 接続メタデータ（`access_token`, `role`, `permissions`, `session_tag`, `description`）とは別。

#### 1.5.3 メッセージID（`Message.id` / `CommandInput.id` / `CommandOutput.id`）

`id` フィールドは個々のメッセージを識別する。

- クライアント送信時: **空文字でよい**。サーバー側で `uuid4().hex[:12]` 形式のIDが自動生成される。
- クライアントが任意のIDを設定して送信することも可能。ACK の `correlation_id` に使用される。
- サーバー→クライアントの応答には常にIDが設定される。

### 1.6 Identity

グループチャットの発話者やアカウント操作対象を表す外部ID。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `provider` | string | 外部ID提供元。例: `discord`, `local`。`subject` と組み合わせてユーザーの不変キーを形成する |
| `subject` | string | provider内の安定ID。ユーザーを一意に識別する不変な値である必要がある（変更されると別Accountとして扱われる） |
| `provider_name` | string | provider側表示名 |
| `metadata` | map<string,string> | guild_id / channel_id等 |

### 1.7 ControlMessage (`BidirectionalStreamRequest.control` / `BidirectionalStreamResponse.control`)

アカウント制御プロトコル。通常の発話では `Message.speaker` から自動joinされるため、明示ControlMessageは任意。

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `action` | string | アクション種別（下記参照） |
| `account_id` | string | Iris内部アカウントID |
| `room_id` | string | 会話ルームID。アカウント制御とpresenceの対象ルーム |
| `display_name` | string | 表示名 |
| `text` | string | サーバーからの応答メッセージ（サーバー→クライアントのみ） |
| `identity` | Identity | 外部ID |
| `profile` | map<string,string> | 更新するプロフィール |
| `metadata` | map<string,string> | action固有メタデータ |

**action 定義**:

| action | 方向 | 説明 | 必須フィールド |
|--------|------|------|---------------|
| `account.identify` | C→S | identity解決/作成、アカウント情報返却（旧 `account.join`） | `identity.provider`, `identity.subject` |
| `account.profile` | C→S, S→C | 現セッションのアカウント情報取得（旧 `account.get`） | なし |
| `account.update` | C→S, S→C | 表示名・プロフィール更新 | `display_name` または `profile` |
| `account.link` | C→S, S→C | 外部ID追加紐付け（旧 `account.link_identity`） | `identity.provider`, `identity.subject` |
| `room.create` | C→S, S→C | ルーム作成 | `text` (ルーム名) |
| `room.list` | C→S, S→C | ルーム一覧取得 | なし |
| `room.info` | C→S, S→C | ルーム情報取得 | `room_id` |
| `room.join` | C→S, S→C | ルーム参加（identityからaccount作成も可） | `room_id`, (`account_id` or `identity`) |
| `room.leave` | C→S, S→C | ルーム退室 | `room_id`, (`account_id` or `identity`) |
| `room.update` | C→S, S→C | ルーム情報更新 | `room_id`, `text` (JSON) |
| `room.delete` | C→S, S→C | ルーム削除 | `room_id` |
| `room.members` | C→S, S→C | ルームメンバー一覧取得 | `room_id` |

**応答 (Server→Client)**:

| action | 説明 |
|--------|------|
| `account.identified` | identify完了応答 |
| `account.profile` | profile取得結果 |
| `account.updated` | update完了応答 |
| `account.linked` | link完了応答 |
| `room.created` | create完了応答 |
| `room.list` | list結果（`text` にJSON配列） |
| `room.info` | info結果（`text` にJSON） |
| `room.joined` | join完了応答 |
| `room.left` | leave完了応答 |
| `room.updated` | update完了応答 |
| `room.deleted` | delete完了応答 |
| `room.members` | members結果（`text` にJSON配列） |

**エラー応答**: エラー時は元のリクエストアクション名（例: `account.identify`）で応答し、`text` に `Error: <message>` を格納する。専用の `account.error` / `room.error` アクションは存在しない。

**自動発行**:
- ルーム入退室時、サーバーは `presence.joined` / `presence.left` を `ControlMessage` として配信する。
- セッション切断時、サーバーは当該セッションを含む全ルームメンバーからセッションIDを除去し、セッションIDが空になったメンバーを自動退室させる。退室時に各ルームに `presence.left` を配信する。

### 1.8 Message (`BidirectionalStreamRequest.message` / `BidirectionalStreamResponse.message`)

Iris の中核メッセージ型。会話テキスト、ストリーミング応答、システム制御信号のすべてをこの型で表現する。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `id` | string | 任意 | メッセージID。空文字可（サーバー自動採番）。ACK相関に使用（§1.5.3） |
| `correlation_id` | string | 任意 | 相関ID。ACKや応答の元メッセージ参照用 |
| `session_id` | string | 任意 | セッションID。空文字可（サーバー上書き）。送信不要（§2.2） |
| `source_role` | string | 任意 | 送信元ロール。クライアント送信時はサーバーが認証ロールで上書き（§1.4） |
| `target_role` | string | 条件付き要 | 配送先ロール。Iris への発話時は `"mind"` が必須。省略すると `"*"` にフォールバックし、Iris は処理しない（§1.4） |
| `direction` | string | 要 | 通信方向。`request` / `response` / `stream` / `event`（§1.2） |
| `msg_type` | string | 要 | メッセージ種別。`chat` / `system` / `proactive` etc（§1.3） |
| `content` | string | 条件付き要 | メッセージ本文。`chat`メッセージでは必須（空文字時はエラー応答）。`interrupt`/`voice_indicator`等では不要 |
| `content_type` | string | 任意 | MIME type。デフォルト `"text/plain"`（§1.5.1） |
| `state` | string | 任意 | ストリーム状態。`thinking` / `speaking` / `done` / `interrupted` |
| `metadata` | map<string,string> | 任意 | 拡張メタデータ。ack_required, account_id, room_id（§1.5.2） |
| `speaker` | Identity | 条件付き要 | 発話者外部ID。Client→Serverの`request`方向では必須（欠落時はエラー応答）。グループチャット・アカウント解決で使用（§1.6） |
| `room_id` | string | 条件付き要 | 会話ルームID。`room.create` 発行の16進UUID。chat/systemメッセージで必須、空の場合はエラー応答（protocol-spec.md §2.2, §4） |

### 1.9 CommandInput (`BidirectionalStreamRequest.command`)

Fast-path コマンド入力。`/` で始まる文字列をコマンドとして処理する。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 任意 | メッセージ種別（予約）。現在未使用 |
| `id` | string | 任意 | メッセージID。空文字可（サーバー自動採番） |
| `session_id` | string | 任意 | セッションID。空文字可（サーバー上書き） |
| `source_role` | string | 任意 | 送信元ロール。クライアント送信時はサーバーが認証ロールで上書き |
| `content` | string | 要 | コマンド文字列。`/` で始める（例: `"/status"`） |

### 1.10 CommandOutput (`BidirectionalStreamResponse.command`)

Fast-path コマンド応答。`/` コマンドの実行結果を返す。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `id` | string | 任意 | メッセージID |
| `correlation_id` | string | 任意 | 元コマンドの `id` と相関 |
| `session_id` | string | 任意 | セッションID |
| `msg_type` | string | 任意 | メッセージ種別（予約） |
| `content` | string | 任意 | コマンド実行結果 |
| `state` | string | 任意 | 実行状態（予約） |
