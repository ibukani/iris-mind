# Iris Mind 通信プロトコル仕様 v2.0

## 1. 概要

Iris Mind は TCP 経由で外部プロセスと通信する。本ドキュメントは**言語非依存**のプロトコル仕様を定義する。

### 設計原則

- **言語非依存**: JSON + UTF-8 エンコーディング
- **セッションベース**: 認証 → セッション確立 → 通信
- **1ポート多重**: 認証・入力・出力すべてを単一TCP接続で多重化
- **Role/Permission 分離**: 権限モデルを `role`（識別子）と `permissions`（権限セット）に分離

## 2. 通信方式

### 2.1 トランスポート

**TCP/IP** (`AF_INET`)

- アドレス: `127.0.0.1:9876`（デフォルト）
- 同一マシン内プロセス間通信専用（デフォルト）
- 設定によりリモート接続可能（`access_token` 必須）

### 2.2 セッション構成

1セッション = 1TCP接続。認証・入力・出力すべてを1本の接続で処理する。

### 2.3 ワイヤー形式（フレーミング）

```
[4バイト: ペイロード長 (big-endian)] [UTF-8 JSON ペイロード]
```

| 部品 | サイズ | エンコーディング |
|------|--------|-----------------|
| ペイロード長 | 4バイト (uint32, big-endian) | バイナリ |
| ペイロード | 可変 (0〜32MB) | UTF-8 JSON |

## 3. プロトコル概要

| 方向 | msg_type | 説明 |
|------|----------|------|
| Client → Server | `auth` | 認証リクエスト |
| Server → Client | `auth_success`, `auth_failure`, `error` | 認証レスポンス |
| Client → Server | 各種 `Message`（`direction:request`） | テキスト入力・システムメッセージ |
| Client → Server | `command` | システムコマンド（`CommandInput` fast-path） |
| Client → Server | `ping` | ハートビート |
| Server → Client | `pong` | ハートビート応答 |
| Server → Client | 各種 `Message`（`direction:response/stream/event`） | 応答・ストリーム・イベント |
| Server → Client | `command` | コマンド応答（`CommandOutput` fast-path） |

## 4. v1.x からの非互換変更

| 変更 | v1.x | v2.0 |
|------|------|------|
| メッセージモデル | `InputMessage`, `OutputMessage`, `InterruptMessage` の3種 | 統一 `Message` モデル |
| 権限 | `SessionRole`（機能別 Enum） | `Permission`（個別権限 Enum）+ `role`（文字列識別子） |
| モード | `ConnectionMode`（INPUT_ONLY/OUTPUT_ONLY/BIDIRECTIONAL） | 削除（Permission で代替） |
| 入力 | `dispatch_text`, `converse_text`, `system` | `chat`, `system` に統合 |
| 出力 | `response`, `proactive`, `stream`, `ack` | すべて `Message` として統一 |
| 中断 | `InterruptMessage`（専用モデル） | `Message(msg_type:"interrupt")` |
| プロアクティブ | `RECEIVE_PROACTIVE` | 削除（`RECEIVE_CHAT` に統合） |
| 認証 | `mode`, `roles` | `role`, `permissions` |

## 5. データ型定義

### 5.1 Permission

| 値 | 説明 |
|----|------|
| `send_chat` | テキスト入力を送信可能 |
| `receive_chat` | 応答を受信可能 |
| `send_command` | `/` コマンドを送信可能 |
| `receive_command` | コマンド結果を受信可能 |
| `receive_log` | ログ・デバッグ情報を受信可能 |
| `interrupt` | 生成中断を要求可能 |
| `execute_action` | アクション実行要求を受信可能 |

### 5.2 Direction

| 値 | 説明 |
|----|------|
| `request` | クライアント→サーバーへのリクエスト |
| `response` | サーバー→クライアントへの単一応答 |
| `stream` | サーバー→クライアントへのストリーミング中継（thinking/speaking/done） |
| `event` | サーバー→クライアントへのイベント通知（ブロードキャスト等） |

### 5.3 msg_type 定義

| msg_type | 方向 | 説明 |
|----------|------|------|
| `chat` | 双方向 | テキスト会話メッセージ |
| `system` | Client→Server | システム制御メッセージ |
| `interrupt` | Client→Server | 生成中断要求 |
| `execute` | Server→Client | アクション実行要求（tools使用時） |
| `execute_result` | Client→Server | アクション実行結果 |
| `ack` | Server→Client | 受信確認（`metadata.ack_required` 時） |
| `error` | Server→Client | エラー通知 |

### 5.4 Message（統一言語モデル）

```json
{
  "msg_type": "chat",
  "session_id": "a1b2c3d4e5f6g7h8",
  "direction": "request",
  "source_role": "cli",
  "target_role": "mind",
  "content": "Hello Iris",
  "content_type": "text/plain",
  "state": null,
  "correlation_id": null,
  "metadata": {}
}
```

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `msg_type` | string | 必須 | - | メッセージ種別 |
| `session_id` | string | 応答時必須 | `""` | セッション識別子（認証後に取得） |
| `direction` | string | 必須 | - | メッセージの方向 |
| `source_role` | string | 必須 | - | 送信元の role（サーバー側で上書き） |
| `target_role` | string | 必須 | `"*"` | 送信先の role（`"*"` は全セッション） |
| `content` | string | 必須 | - | メッセージ本文 |
| `content_type` | string | 任意 | `"text/plain"` | コンテンツタイプ（将来の拡張用） |
| `state` | string | 任意 | null | ストリーム状態（`thinking`/`speaking`/`done`） |
| `correlation_id` | string | 任意 | null | 応答連鎖の識別子 |
| `metadata` | object | 任意 | `{}` | 拡張メタデータ |

### 5.5 AuthMessage（Client → Server）

```json
{
  "msg_type": "auth",
  "access_token": "",
  "role": "cli",
  "permissions": ["send_chat", "receive_chat"],
  "identity": "my-client",
  "description": "My custom client"
}
```

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `msg_type` | string | 必須 | `"auth"` | 固定値 |
| `access_token` | string | 条件付き | null | トークン認証が設定されている場合は必須 |
| `role` | string | 任意 | `"external"` | クライアントの識別名（ルーティングに使用） |
| `permissions` | Permission[] | 任意 | `[]` | クライアントに付与する権限リスト |
| `identity` | string | 任意 | `""` | クライアントの識別情報 |
| `description` | string | 任意 | `""` | 接続の説明 |

### 5.6 ControlMessage（Server → Client）

```json
{
  "msg_type": "auth_success",
  "session_id": "a1b2c3d4e5f6g7h8"
}
```

```json
{
  "msg_type": "auth_failure",
  "error_message": "invalid access_token"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | `auth_success` / `auth_failure` / `error` |
| `session_id` | string | success時 | 割り当てられたセッションID |
| `error_message` | string | failure時 | エラー詳細 |

### 5.7 CommandInput（Client → Server）

```json
{
  "msg_type": "command",
  "session_id": "a1b2c3d4e5f6g7h8",
  "content": "/help"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | `"command"` |
| `session_id` | string | 必須 | 認証後に取得 |
| `content` | string | 必須 | `/` で始まるコマンド文字列 |

### 5.8 CommandOutput（Server → Client）

```json
{
  "msg_type": "command",
  "session_id": "a1b2c3d4e5f6g7h8",
  "content": "Available commands: /help, /status, ..."
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | `"command"` |
| `correlation_id` | string | 任意 | 入力の CommandInput.id に対応 |
| `session_id` | string | 必須 | 応答先セッション |
| `content` | string | 必須 | コマンド実行結果 |

### 5.9 Ping / Pong

```json
{"msg_type": "ping"}
{"msg_type": "pong"}
```

## 6. 接続シーケンス

### 6.1 通常フロー

```
Client                          Kernel
  │                                │
  ├── TCP connect ────────────────►│
  │                                │
  ├── AuthMessage ────────────────►│
  │                                ├── トークン検証・セッション生成
  │◄─── auth_success ─────────────┤
  │    (session_id を受領)         │
  │                                │
  ├── Message(direction:request,   │
  │     target_role:"mind",        │
  │     msg_type:"chat",           │
  │     content:"Hello") ────────► ├── MessageEvent → Memory → Agency → ...
  │                                │
  │◄─── Message(direction:stream,  │
  │     state:"thinking") ────────┤
  │◄─── Message(direction:stream,  │
  │     state:"speaking",          │
  │     content:"Hello!") ────────┤
  │◄─── Message(direction:stream,  │
  │     state:"done") ────────────┤
  │◄─── Message(direction:response,│
  │     content:"Hello! How can    │
  │     I help you today?") ──────┤
```

### 6.2 コマンドフロー（Fast-Path）

```
Client                          Kernel
  │                                │
  ├── CommandInput ───────────────►│
  │    (content: "/status")        ├── CommandHandler で直接処理
  │◄─── CommandOutput ────────────┤
  │    (content: "Status: OK")     │
```

コマンドは Message ではなく `CommandInput`/`CommandOutput` という専用モデルで処理される。EventBus を経由しない Fast-Path。

### 6.3 中断フロー

```
Client                          Kernel
  │                                │
  ├── Message(direction:request,   │
  │     msg_type:"interrupt",      │
  │     target_role:"mind") ──────►│
```

`msg_type: "interrupt"` の Message で生成中断を要求する（現状中断機構は構築中）。

## 7. 権限モデル

### 7.1 Permission チェック

セッション認証時に宣言された `permissions` に基づき、サーバーは出力配送をフィルタリングする。

| 出力 msg_type | 必要な Permission |
|--------------|-------------------|
| `chat` | `receive_chat` |
| `proactive` | `receive_chat` |
| `system` | `receive_chat` |
| `ack` | `receive_chat` |
| `error` | `receive_chat` |
| `execute` | `execute_action` |
| `interrupt` | `interrupt` |

### 7.2 Role ベースルーティング

`Message.target_role` で配送先を指定:
- `"*"` で全アクティブセッションにブロードキャスト
- 特定の role 名（例: `"cli"`）で該当 role の全セッションに配送
- `session_id` が指定された場合は当該セッションに直接配送（最優先）

## 8. 実装例

### 8.1 Python（asyncio）

```python
import json
import socket
import struct

def send_msg(sock: socket.socket, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack("!I", len(payload)) + payload)

def recv_msg(sock: socket.socket) -> dict:
    raw_len = sock.recv(4)
    length = struct.unpack("!I", raw_len)[0]
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise ConnectionError("Connection closed")
        payload += chunk
    return json.loads(payload.decode("utf-8"))

# 接続例
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("127.0.0.1", 9876))

# 認証
send_msg(sock, {
    "msg_type": "auth",
    "role": "cli",
    "permissions": ["send_chat", "receive_chat"],
})
resp = recv_msg(sock)
assert resp["msg_type"] == "auth_success"
session_id = resp["session_id"]

# メッセージ送信
send_msg(sock, {
    "msg_type": "chat",
    "session_id": session_id,
    "direction": "request",
    "source_role": "cli",
    "target_role": "mind",
    "content": "Hello Iris!",
})

# 応答受信
while True:
    msg = recv_msg(sock)
    if msg.get("direction") == "response":
        print(f"Iris: {msg['content']}")
        break
    elif msg.get("state") == "thinking":
        print("Iris is thinking...")
```

### 8.2 Python（コマンド送信）

```python
send_msg(sock, {
    "msg_type": "command",
    "session_id": session_id,
    "content": "/status",
})
resp = recv_msg(sock)
print(resp["content"])
```

### 8.3 Rust

```rust
use std::io::{Read, Write};
use std::net::TcpStream;
use serde_json::json;

fn send_msg(stream: &mut TcpStream, data: &serde_json::Value) {
    let payload = serde_json::to_string(data).unwrap();
    let len = payload.len() as u32;
    stream.write_all(&len.to_be_bytes()).unwrap();
    stream.write_all(payload.as_bytes()).unwrap();
}

fn recv_msg(stream: &mut TcpStream) -> serde_json::Value {
    let mut len_buf = [0u8; 4];
    stream.read_exact(&mut len_buf).unwrap();
    let len = u32::from_be_bytes(len_buf) as usize;
    let mut buf = vec![0u8; len];
    stream.read_exact(&mut buf).unwrap();
    serde_json::from_slice(&buf).unwrap()
}

// 認証
let mut stream = TcpStream::connect("127.0.0.1:9876").unwrap();
send_msg(&mut stream, &json!({
    "msg_type": "auth",
    "role": "cli",
    "permissions": ["send_chat", "receive_chat"],
}));
```

## 9. エラーハンドリング

| 状況 | 動作 |
|------|------|
| 認証失敗 | Server は `auth_failure` を返して接続を切断 |
| 認証前のメッセージ受信 | Server は警告ログ出力してメッセージを無視 |
| 不正な JSON | Server は接続を切断 |
| 接続断 | Server はセッション情報を削除 |
| 不明な msg_type | Server は警告ログ出力してメッセージを無視 |
