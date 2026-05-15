# Iris Kernel 通信プロトコル仕様 v3.0

## 1. 概要

Iris Kernel は Named Pipe 経由で外部プロセスと通信する。このドキュメントは**言語非依存**のプロトコル仕様を定義する。任意のプログラミング言語から実装可能。

### 設計原則

- **言語非依存**: JSON + UTF-8 エンコーディング。特定言語のライブラリに依存しない
- **セッションベース**: 認証 → セッション確立 → 通信 の明確な段階
- **3-Pipe分離**: 制御・入力・出力を物理的に分離し、セキュリティと拡張性を確保

## 2. 通信方式

### 2.1 トランスポート

**Windows Named Pipes** (`multiprocessing.connection` の `AF_PIPE` ファミリ)

- Pipe アドレス: `\\.\pipe\iris-kernel-<name>`
- 双方向通信可能
- 同一マシン内プロセス間通信専用

**将来の拡張**: TCP/IP (`AF_INET`) への移行も設計上可能

### 2.2 Pipe 構成

| Pipe 名 | 方向 | 用途 |
|---------|------|------|
| `\\.\pipe\iris-kernel-control` | 双方向 | 認証ハンドシェイク、セッション管理 |
| `\\.\pipe\iris-kernel-input` | 外部→Kernel | ユーザー入力、コマンド |
| `\\.\pipe\iris-kernel-output` | Kernel→外部 | 応答、自律発話、ストリーム |

### 2.3 シリアライズ

- **形式**: JSON (UTF-8 エンコーディング)
- **フレーミング**: `send_bytes()` / `recv_bytes()` によるメッセージ境界保証
- **最大サイズ**: デフォルト 32MB

**ワイヤー形式例**:
```json
{"msg_type": "text", "session_id": "a1b2c3d4e5f6g7h8", "content": "hello", "id": "abc123"}
```

## 3. 接続シーケンス

### 3.1 認証ハンドシェイク

```
クライアント                           Iris Kernel
    │                                      │
    │──── Control Pipe 接続 ────────────────→│
    │                                      │
    │── AuthMessage (JSON) ────────────────→│
    │  {                                    │
    │    "msg_type": "auth",                │
    │    "mode": "bidirectional",           │
    │    "auth_token": "..." (任意)         │
    │  }                                    │
    │                                      │
    │←── ControlMessage (JSON) ─────────────│
    │  {                                    │
    │    "msg_type": "auth_success",        │
    │    "session_id": "a1b2c3d4e5f6g7h8"   │
    │  }                                    │
    │                                      │
    │──── Input Pipe 接続 ──────────────────→│
    │  (session_id を使用)                  │
    │                                      │
    │──── Output Pipe 接続 ─────────────────→│
    │  (session_id を使用)                  │
    │                                      │
    │◄─── 双方向通信開始 ───────────────────►│
```

### 3.2 接続モード

`AuthMessage.mode` で指定:

| モード | 説明 | 必要な接続 |
|--------|------|-----------|
| `bidirectional` | 入出力双方向 | Input + Output |
| `input_only` | 入力のみ | Input のみ |
| `output_only` | 出力のみ | Output のみ |

### 3.3 セッション状態遷移

```
[Control接続] → AUTHENTICATING
                    │
                    ├─ mode=input_only  → WAITING_INPUT → [Input接続] → ACTIVE
                    ├─ mode=output_only → WAITING_OUTPUT → [Output接続] → ACTIVE
                    └─ mode=bidirectional → WAITING_INPUT → [Input接続] → WAITING_OUTPUT → [Output接続] → ACTIVE
```

## 4. メッセージ形式

### 4.1 AuthMessage (Control Pipe)

認証リクエスト。Control Pipe 接続後に最初に送信。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | 常に `"auth"` |
| `mode` | string | 必須 | `"bidirectional"`, `"input_only"`, `"output_only"` |
| `auth_token` | string | 任意 | 認証トークン（将来の拡張用） |

**リクエスト例**:
```json
{
  "msg_type": "auth",
  "mode": "bidirectional",
  "auth_token": "my-secret-token"
}
```

### 4.2 ControlMessage (Control Pipe)

認証レスポンス。Kernel から返される。

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `msg_type` | string | 必須 | `"auth_success"`, `"auth_failure"`, `"error"` |
| `session_id` | string | 条件付き | 成功時のみ。16文字のセッションID |
| `error_message` | string | 条件付き | 失敗時のみ。エラー理由 |

**成功レスポンス例**:
```json
{
  "msg_type": "auth_success",
  "session_id": "a1b2c3d4e5f6g7h8"
}
```

**失敗レスポンス例**:
```json
{
  "msg_type": "auth_failure",
  "error_message": "invalid auth_token"
}
```

### 4.3 InputMessage (Input Pipe)

外部クライアントから Kernel への入力メッセージ。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `id` | string | 必須 | 自動生成 | メッセージID (12文字) |
| `session_id` | string | 必須 | - | 認証で取得したセッションID |
| `source` | string | 必須 | - | 送信元識別子 ("cli", "web", etc.) |
| `msg_type` | string | 必須 | `"text"` | `"text"`, `"command"`, `"system"` |
| `content` | string | 必須 | - | メッセージ本文 |
| `content_type` | string | 任意 | `"text/plain"` | コンテンツタイプ |
| `metadata` | object | 任意 | `{}` | 拡張メタデータ |

**テキスト入力例**:
```json
{
  "id": "msg001",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "msg_type": "text",
  "content": "こんにちは"
}
```

**コマンド入力例**:
```json
{
  "id": "msg002",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "msg_type": "command",
  "content": "/status"
}
```

### 4.4 OutputMessage (Output Pipe)

Kernel から外部クライアントへの出力メッセージ。

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `id` | string | 必須 | 自動生成 | メッセージID (12文字) |
| `session_id` | string | 必須 | - | 宛先セッションID |
| `correlation_id` | string | 任意 | - | 対応する入力メッセージのID |
| `msg_type` | string | 必須 | - | `"stream"`, `"response"`, `"proactive"`, `"command"`, `"error"`, `"ack"` |
| `content` | string | 必須 | - | メッセージ本文 |
| `content_type` | string | 任意 | `"text/plain"` | コンテンツタイプ |
| `destinations` | string[] | 任意 | - | 出力先フィルタ |
| `metadata` | object | 任意 | `{}` | 拡張メタデータ |

**ストリーム応答例**:
```json
{
  "id": "out001",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg001",
  "msg_type": "stream",
  "content": "Hello"
}
```

**最終応答例**:
```json
{
  "id": "out002",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg001",
  "msg_type": "response",
  "content": "Hello! How can I help you?",
  "metadata": {
    "model": "qwen3.5:9b",
    "done": true
  }
}
```

**自律発話例**:
```json
{
  "id": "out003",
  "session_id": "a1b2c3d4e5f6g7h8",
  "msg_type": "proactive",
  "content": "そろそろ休憩しませんか？"
}
```

### 4.5 コマンド一覧

| コマンド | 説明 | 応答 |
|---------|------|------|
| `/status` | Kernel の状態確認 | 状態情報 |
| `/shutdown` | グレースフルシャットダウン | `"Shutting down..."` |
| `/sleep` | エージェント休止 | 確認メッセージ |
| `/wakeup` | エージェント再開 | 確認メッセージ |
| `/help` | コマンド一覧 | コマンドリスト |
| `/compact` | 会話履歴の圧縮 | 確認メッセージ |

## 5. ACK メカニズム

重要なメッセージには応答確認 (ACK) が使用される。

- `metadata.ack_required: true` を設定すると、Kernel は `msg_type: "ack"` を返す
- ACK メッセージの `correlation_id` には元のメッセージの `id` が設定される

**ACK リクエスト例**:
```json
{
  "id": "msg003",
  "session_id": "a1b2c3d4e5f6g7h8",
  "source": "cli",
  "msg_type": "command",
  "content": "/shutdown",
  "metadata": {
    "ack_required": true
  }
}
```

**ACK 応答例**:
```json
{
  "id": "ack001",
  "session_id": "a1b2c3d4e5f6g7h8",
  "correlation_id": "msg003",
  "msg_type": "ack",
  "content": "ack:msg003"
}
```

## 6. エラーハンドリング

| 状況 | Kernel の動作 | クライアントの動作 |
|------|--------------|-------------------|
| 認証失敗 | ControlMessage (auth_failure) 送信後、接続切断 | エラー表示、再試行 |
| 無効な session_id | メッセージを拒否、ログ出力 | 再接続、再認証 |
| 不正なメッセージ | ログ出力、接続切断 | ログ出力、再接続 |
| 接続断 (予期せず) | 該当スレッド終了、セッションクリーンアップ | 指数バックオフで再接続 |
| セッションタイムアウト | セッション削除、接続切断 | 再認証からやり直し |

## 7. 実装ガイドライン

### 7.1 最小クライアント実装 (疑似コード)

```
# 1. Control Pipe に接続
control = connect("\\\\.\\pipe\\iris-kernel-control")

# 2. 認証リクエスト送信
auth = {
    "msg_type": "auth",
    "mode": "bidirectional"
}
send(control, json.dumps(auth))

# 3. 認証レスポンス受信
response = json.loads(recv(control))
session_id = response["session_id"]

# 4. Input/Output Pipe に接続
input_pipe = connect("\\\\.\\pipe\\iris-kernel-input")
output_pipe = connect("\\\\.\\pipe\\iris-kernel-output")

# 5. 入力メッセージ送信
msg = {
    "session_id": session_id,
    "source": "my-client",
    "msg_type": "text",
    "content": "hello"
}
send(input_pipe, json.dumps(msg))

# 6. 出力メッセージ受信
while True:
    output = json.loads(recv(output_pipe))
    print(output["content"])
```

### 7.2 言語別実装ノート

**Python**:
```python
from multiprocessing.connection import Client
conn = Client(r"\\.\pipe\iris-kernel-control", family="AF_PIPE")
```

**C# / .NET**:
```csharp
using System.IO.Pipes;
var pipe = new NamedPipeClientStream(".", "iris-kernel-control", PipeDirection.InOut);
pipe.Connect();
```

**C++ (Windows API)**:
```cpp
HANDLE hPipe = CreateFile(
    L"\\\\.\\pipe\\iris-kernel-control",
    GENERIC_READ | GENERIC_WRITE,
    0, NULL, OPEN_EXISTING, 0, NULL
);
```

**Node.js**:
```javascript
// 外部ライブラリ必要 (例: node-named-pipe)
const pipe = new NamedPipeClient("\\\\.\\pipe\\iris-kernel-control");
```

### 7.3 再接続ロジック

```
function connect_with_retry():
    max_retries = 5
    backoff = 1.0

    for i in 1..max_retries:
        try:
            return connect()
        except ConnectionError:
            sleep(backoff)
            backoff *= 2

    raise ConnectionFailed
```

## 8. セキュリティ考慮事項

- **認証**: 現在は `session_id` のみで認証。将来的に `auth_token` 検証を追加予定
- **セッションID**: サーバー側で UUID4 生成。クライアントは推測不可能
- **ローカル通信**: 現時点で同一マシン内限定。外部ネットワークからの接続は不可
- **パイプ権限**: Windows の ACL でアクセス制御可能（将来の拡張）

## 9. 将来の拡張

### 9.1 TCP/IP 対応

`AF_PIPE` → `AF_INET` に変更するだけで同一プロトコルが動作:

```
address: ("127.0.0.1", 9876)
family: "AF_INET"
```

### 9.2 TLS 暗号化

TCP 移行時に TLS 層を追加可能。認証トークンとの組み合わせでセキュアな通信を実現。

### 9.3 複数セッション

1クライアントが複数の `session_id` を取得可能。用途別にセッションを分離できる。
