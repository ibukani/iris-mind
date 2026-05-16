# Iris Kernel 通信プロトコル仕様 v4.0

## 1. 概要

Iris Kernel は TCP 経由で外部プロセスと通信する。このドキュメントは**言語非依存**のプロトコル仕様を定義する。任意のプログラミング言語から実装可能。

### 設計原則

- **言語非依存**: JSON + UTF-8 エンコーディング。特定言語のライブラリに依存しない
- **セッションベース**: 認証 → セッション確立 → 通信 の明確な段階
- **1ポート多重**: 認証・入力・出力すべてを単一のTCP接続で多重化

## 2. 通信方式

### 2.1 トランスポート

**TCP/IP** (`AF_INET`)

- アドレス: `127.0.0.1:9876`（デフォルト）
- 双方向通信可能
- 同一マシン内プロセス間通信専用（デフォルト）
- 設定によりリモート接続可能（その場合は `access_token` 必須）

### 2.2 セッション構成

1セッション = 1TCP接続。認証・入力・出力すべてを1本の接続で処理する。

### 2.3 ワイヤー形式（フレーミング）

全メッセージは以下の形式で送受信する:

```
[4バイト: ペイロード長 (big-endian)] [UTF-8 JSON ペイロード]
```

| 部品 | サイズ | エンコーディング |
|------|--------|-----------------|
| ペイロード長 | 4バイト (uint32, big-endian) | バイナリ |
| ペイロード | 可変 (0〜32MB) | UTF-8 JSON |

**例**: メッセージ `{"msg_type":"auth"}` のワイヤー表現:

```
00 00 00 18 7B 22 6D 73 67 5F 74 79 70 65 22 3A 22 61 75 74 68 22 7D
├── length=24 ──┤ ├── UTF-8 JSON (24 bytes) ──────────────────────────┤
```

## 3. プロトコル概要（メッセージの方向性）

接続上の全メッセージは `msg_type` フィールドで種類を判別する。

| 方向 | msg_type 一覧 | 説明 |
|------|--------------|------|
| Client → Server | `auth` | 認証リクエスト |
| Server → Client | `auth_success`, `auth_failure`, `error` | 認証レスポンス |
| Client → Server | `text`, `command`, `system` | ユーザー入力 |
| Server → Client | `response`, `stream`, `proactive`, `ack` | 出力メッセージ |

クライアントは認証成功後、**同一接続で**入力送信と出力受信を並行して行う。

## 4. 接続シーケンス

### 4.1 認証ハンドシェイク

```mermaid
---
config:
  theme: base
  themeVariables:
    primaryColor: "#e8f0fe"
    secondaryColor: "#e6f4ea"
    tertiaryColor: "#fce8e6"
---
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Kernel as Iris Kernel

    Client->>+Kernel: TCP connect (127.0.0.1:9876)
    Client->>+Kernel: AuthMessage (msg_type: auth, mode: bidirectional)
    Kernel-->>-Client: auth_success (session_id: "a1b2c3d4...")
    Note over Client,Kernel: 以降、同一接続で双方向通信
```

### 4.2 接続モード

`AuthMessage.mode` で指定:

| モード | 説明 |
|--------|------|
| `bidirectional` | 入出力双方向（デフォルト） |
| `input_only` | 入力のみ。Kernelは出力を送信しない |
| `output_only` | 出力のみ。Kernelは入力を受け付けない |

### 4.3 セッション状態遷移

```mermaid
---
config:
  theme: base
  themeVariables:
    primaryColor: "#e8f0fe"
    secondaryColor: "#e6f4ea"
---
stateDiagram-v2
    [*] --> AUTHENTICATING : TCP接続 / AuthMessage
    AUTHENTICATING --> ACTIVE : 認証成功 (auth_success)
    AUTHENTICATING --> [*] : 認証失敗 (auth_failure → 切断)
```

認証成功後、即座に ACTIVE 状態となる。Input/Output の個別接続は不要。

### 4.4 完全な通信フロー（テキスト入力〜応答受信）

```mermaid
---
config:
  theme: base
  themeVariables:
    primaryColor: "#e8f0fe"
    secondaryColor: "#e6f4ea"
    tertiaryColor: "#fef7e0"
---
sequenceDiagram
    autonumber
    participant Client as クライアント
    participant Kernel as Iris Kernel

    rect rgb(232, 240, 254)
        Note over Client,Kernel: 認証
        Client->>+Kernel: AuthMessage (msg_type: auth)
        Kernel-->>-Client: auth_success (session_id: "sess001")
    end

    rect rgb(230, 245, 225)
        Note over Client,Kernel: 入力・応答
        Client->>+Kernel: InputMessage (msg_type: text, content: "hello")
        Kernel-->>Client: stream (content: "Hello")
        Kernel-->>Client: stream (content: "! How")
        Kernel-->>Client: stream (content: " can I help?")
        Kernel-->>Client: stream (content: "", metadata: {done: true})
        Kernel-->>-Client: response (content: "Hello! How can I help?")
    end
```

**出力ストリームの終端判定**: `msg_type="stream"` で `metadata.done == true` が最終チャンクの合図。その後 `msg_type="response"` で完全な応答テキストが届く。

## 5. メッセージ形式

### 5.1 AuthMessage（Client → Server）

認証リクエスト。TCP接続後に最初に送信するメッセージ。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | 常に `"auth"` |
| `mode` | string | 任意 | `"bidirectional"`（デフォルト）, `"input_only"`, `"output_only"` |
| `access_token` | string | 条件付き | サーバー側で設定されている場合は必須 |

```json
{
  "msg_type": "auth",
  "mode": "bidirectional",
  "access_token": "my-secret-token"
}
```

### 5.2 ControlMessage（Server → Client）

認証レスポンス。Kernel から返される。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | `"auth_success"`, `"auth_failure"`, `"error"` |
| `session_id` | string | 条件付き | 成功時のみ。16文字のセッションID |
| `error_message` | string | 条件付き | 失敗時のみ。エラー理由 |

**成功**:
```json
{
  "msg_type": "auth_success",
  "session_id": "a1b2c3d4e5f6g7h8"
}
```

**失敗**:
```json
{
  "msg_type": "auth_failure",
  "error_message": "invalid access_token"
}
```

### 5.3 InputMessage（Client → Server）

外部クライアントから Kernel への入力メッセージ。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `msg_type` | string | 必須 | - | `"text"`, `"command"`, `"system"` |
| `id` | string | 任意 | 自動生成 | メッセージID (12文字) |
| `session_id` | string | 必須 | - | 認証で取得したセッションID |
| `source` | string | 必須 | - | 送信元識別子 (`"cli"`, `"web"`, etc.) |
| `content` | string | 必須 | - | メッセージ本文 |
| `content_type` | string | 任意 | `"text/plain"` | コンテンツタイプ |
| `metadata` | object | 任意 | `{}` | 拡張メタデータ |

**テキスト入力**:
```json
{
  "msg_type": "text",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "content": "こんにちは"
}
```

**コマンド入力**:
```json
{
  "msg_type": "command",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "content": "/status"
}
```

### 5.4 OutputMessage（Server → Client）

Kernel から外部クライアントへの出力メッセージ。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `msg_type` | string | 必須 | - | `"response"`, `"stream"`, `"proactive"`, `"ack"` |
| `id` | string | 任意 | 自動生成 | メッセージID (12文字) |
| `session_id` | string | 必須 | - | 宛先セッションID |
| `correlation_id` | string | 任意 | - | 対応する入力メッセージのID |
| `content` | string | 必須 | - | メッセージ本文 |
| `content_type` | string | 任意 | `"text/plain"` | コンテンツタイプ |
| `destinations` | string[] | 任意 | - | 出力先フィルタ |
| `metadata` | object | 任意 | `{}` | 拡張メタデータ |

**ストリーム応答（途中）**:
```json
{
  "msg_type": "stream",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg001",
  "content": "Hello"
}
```

**ストリーム応答（最終）** — `metadata.done = true` が終端:
```json
{
  "msg_type": "stream",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg001",
  "content": "",
  "metadata": {
    "done": true
  }
}
```

**完全な応答（ストリーム終了後に1回送信）**:
```json
{
  "msg_type": "response",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg001",
  "content": "Hello! How can I help you?",
  "metadata": {
    "model": "qwen3.5:9b"
  }
}
```

**自律発話（ユーザー入力なしでKernelが自発的に送信）**:
```json
{
  "msg_type": "proactive",
  "session_id": "a1b2c3d4e5f6g7h8",
  "content": "そろそろ休憩しませんか？"
}
```

## 6. ACK メカニズム

入力メッセージに `metadata.ack_required: true` を設定すると、Kernel は `msg_type: "ack"` の OutputMessage を返す。
ACK メッセージの `correlation_id` には元のメッセージの `id` が設定される。

**ACK リクエスト**:
```json
{
  "msg_type": "command",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "content": "/shutdown",
  "metadata": {
    "ack_required": true
  }
}
```

**ACK 応答**:
```json
{
  "msg_type": "ack",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg003",
  "content": "ack:msg003"
}
```

## 7. コマンド一覧

`msg_type="command"` で送信すると、スラッシュコマンドとして解釈される。

| コマンド | 説明 | 応答の例 |
|---------|------|---------|
| `/status` | Kernel の状態確認 | `"Status: IDLE, uptime: 1h"` |
| `/shutdown` | グレースフルシャットダウン | `"Shutting down..."` |
| `/sleep` | エージェント休止 | `"Iris is going to sleep."` |
| `/wakeup` | エージェント再開 | `"Iris is awake."` |
| `/help` | コマンド一覧 | `"Available commands: /status, /shutdown..."` |
| `/compact` | 会話履歴の圧縮 | `"Conversation compacted."` |

応答は `msg_type="command"` の OutputMessage として返される。

## 8. エラーハンドリング

| 状況 | Kernel の動作 | クライアントの動作 |
|------|--------------|-------------------|
| 認証失敗 | `auth_failure` 送信後、接続切断 | エラー表示、再試行 |
| 無効な session_id | メッセージを無視、ログ出力 | 再接続 → 再認証 |
| 不正なメッセージ（JSONパース失敗等） | ログ出力、接続切断 | ログ出力、再接続 |
| 接続断（予期せず） | 該当スレッド終了、セッションクリーンアップ | 指数バックオフで再接続 |
| セッションタイムアウト | セッション削除、接続切断 | 再認証からやり直し |

## 9. 実装例（言語別）

### 9.1 最小クライアント（Python — 生ソケット版）

以下のコードはワイヤー形式に従った**リファレンス実装**。全言語の実装はこの構造を模倣すればよい。

```python
import json
import socket
import struct

class IrisClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((host, port))
        self._buf = b""

    # ── フレーミング ──────────────────────────────────────
    def _send_frame(self, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._sock.sendall(struct.pack("!I", len(data)) + data)

    def _recv_frame(self) -> dict:
        while len(self._buf) < 4:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed")
            self._buf += chunk
        size = struct.unpack("!I", self._buf[:4])[0]
        self._buf = self._buf[4:]
        while len(self._buf) < size:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed")
            self._buf += chunk
        payload = self._buf[:size]
        self._buf = self._buf[size:]
        return json.loads(payload.decode("utf-8"))

    # ── 認証 ──────────────────────────────────────────────
    def authenticate(self, access_token: str = "") -> str:
        msg = {"msg_type": "auth", "mode": "bidirectional"}
        if access_token:
            msg["access_token"] = access_token
        self._send_frame(msg)
        resp = self._recv_frame()
        if resp["msg_type"] != "auth_success":
            raise RuntimeError(f"Auth failed: {resp.get('error_message', 'unknown')}")
        self._session_id = resp["session_id"]
        return self._session_id

    # ── 入力送信 ──────────────────────────────────────────
    def send_input(self, text: str, source: str = "cli") -> None:
        self._send_frame({
            "msg_type": "text",
            "session_id": self._session_id,
            "source": source,
            "content": text,
        })

    # ── 出力受信（1メッセージ） ────────────────────────────
    def recv_output(self) -> dict:
        return self._recv_frame()

    # ── 出力受信（ストリーム完了までまとめて受信） ──────────
    def recv_response(self) -> list[dict]:
        messages = []
        while True:
            msg = self._recv_frame()
            messages.append(msg)
            if msg.get("metadata", {}).get("done"):
                break
            if msg["msg_type"] == "response":
                break
        return messages

    def close(self) -> None:
        self._sock.close()

# ── 使用例 ────────────────────────────────────────────────
client = IrisClient()
session_id = client.authenticate()
client.send_input("hello")
for msg in client.recv_response():
    if msg["msg_type"] == "stream" and msg["content"]:
        print(msg["content"], end="")
    elif msg["msg_type"] == "response":
        print(f"\n[complete] {msg['content']}")
client.close()
```

### 9.2 Python — multiprocessing.connection 版

```python
from multiprocessing.connection import Client

conn = Client(("127.0.0.1", 9876), family="AF_INET")
conn.send_bytes(json.dumps({"msg_type": "auth"}).encode("utf-8"))
resp = json.loads(conn.recv_bytes().decode("utf-8"))
```

**注意**: `multiprocessing.connection` の内部フレーミング形式は標準ライブラリの実装詳細であり、他言語からの互換性は保証されない。他言語で実装する場合は **9.1 のワイヤー形式** に従うこと。

### 9.3 C# / .NET

```csharp
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

using var client = new TcpClient("127.0.0.1", 9876);
var stream = client.GetStream();

byte[] Send(Dictionary<string, object> obj) {
    var json = JsonSerializer.Serialize(obj);
    var data = Encoding.UTF8.GetBytes(json);
    var len = BitConverter.GetBytes(data.Length); // big-endian
    if (BitConverter.IsLittleEndian) Array.Reverse(len);
    stream.Write(len);
    stream.Write(data);
}

byte[] buf = new byte[4];
stream.Read(buf, 0, 4);
if (BitConverter.IsLittleEndian) Array.Reverse(buf);
int size = BitConverter.ToInt32(buf);
// 読み捨て… 完全な実装は9.1の構造を参照
```

### 9.4 Rust

```rust
use std::io::{Read, Write};
use std::net::TcpStream;

let mut stream = TcpStream::connect("127.0.0.1:9876")?;
let data = br#"{"msg_type":"auth","mode":"bidirectional"}"#;
let len = (data.len() as u32).to_be_bytes();
stream.write_all(&len)?;
stream.write_all(data)?;
```

### 9.5 Node.js

```javascript
const net = require('net');

function createFrame(obj) {
    const data = Buffer.from(JSON.stringify(obj), 'utf-8');
    const header = Buffer.alloc(4);
    header.writeUInt32BE(data.length, 0);
    return Buffer.concat([header, data]);
}

const client = net.createConnection(9876, '127.0.0.1', () => {
    client.write(createFrame({ msg_type: 'auth', mode: 'bidirectional' }));
});
```

## 10. セキュリティ

- **認証**: `access_token` によるトークン検証をサポート。`config.yaml` の `session.access_token` または環境変数 `IRIS_ACCESS_TOKEN` で指定
- **ローカル限定**: デフォルトでは `127.0.0.1` にバインド。リモート接続を許可する場合は `access_token` 必須
- **TLS**: 現バージョンでは未対応（将来の拡張）
