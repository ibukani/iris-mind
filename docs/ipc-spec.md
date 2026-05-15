# IPC プロトコル仕様 v1.0

## 1. 概要

Kernel / Input / Output の3プロセス間の通信方式を定義する。

## 2. 通信方式

### 2.1 Windows Named Pipes

`multiprocessing.connection` モジュールの `AF_PIPE` ファミリを使用する。

```python
# Kernel 側 (Listener)
listener = multiprocessing.connection.Listener(
    address=r"\\.\pipe\iris-kernel",
    family="AF_PIPE",
)

# クライアント側 (Client)
conn = multiprocessing.connection.Client(
    address=r"\\.\pipe\iris-kernel",
    family="AF_PIPE",
)
```

### 2.2 Pipe アドレス体系

| Pipe 名 | 方向 | 用途 |
|---------|------|------|
| `\\.\pipe\iris-kernel` | Kernel→Output | Kernel (Client/OutputManager) から Output Process (Listener) への出力送信 |
| `\\.\pipe\iris-kernel-input` | Input→Kernel | Input Process (Client) から Kernel (Listener/InputManager) へのユーザー入力転送 |

各 Pipe は独立した Listener を持つ（単一Listenerではない）。各 Manager は接続ごとにスレッドを割り当てる。

### 2.3 シリアライズ

JSON Lines 形式を使用する。`send_bytes()` / `recv_bytes()` でフレーミングする。

```python
# 送信
data = msg.model_dump_json()
conn.send_bytes(data.encode("utf-8"))

# 受信
raw = conn.recv_bytes().decode("utf-8")
msg = InputMessage.model_validate_json(raw)
```

**ワイヤー形式** (他言語から読み書きする場合):

```
{"msg_type": "text", "source": "cli", "content": "hello", "id": "abc123"}
```

**制約**:
- `send_bytes()` / `recv_bytes()` がフレーミングを内部処理
- 最大メッセージサイズはデフォルトで 32MB（要調整時は別途指定）

### 2.4 Replay ファイル形式

デバッグ用に、送受信されたイベントを JSONL 形式で記録する。

```jsonl
{"msg_type": "text", "source": "cli", "content": "hello", "id": "abc123"}
{"msg_type": "stream", "content": "Hello ", "id": "xyz789", "correlation_id": "abc123", "metadata": {}}
{"msg_type": "response", "content": "...", "id": "...", "correlation_id": "abc123", "metadata": {"model": "qwen3.5:9b"}}
```

`ReplayableTransport` クラスがこの形式で記録する。再生用クラス（`ReplayTransport`）は未実装。

## 3. 接続ライフサイクル

### 3.1 起動シーケンス

```
Kernel Process:
  1. AgentKernel.startup() — 内部イベント購読 + タイマースレッド開始
  2. OutputManager.start() — Output Process (Listener) に Client 接続
  3. InputManager.start() — PipeServer(iris-kernel-input) 起動 + 受付スレッド開始
  4. 子プロセス起動: output_main (Listener 起動待ち)
  5. 子プロセス起動: input_main → iris-kernel-input に Client 接続

Input Process:
  1. Kernel の input Pipe に Client 接続
  2. InputMessage の送信を開始 (input() ループ)

Output Process:
  1. PipeServer(iris-kernel) 起動 + 受付スレッド開始
  2. Kernel からの接続を待機
  3. 受信ループ開始 (OutputMessage 受信 → 表示)
```

### 3.2 切断と再接続

- クライアント切断 → Kernel は該当スレッドをクリーンアップ
- Kernel 切断 → 全クライアントが `EOFError` を受信 → 再接続待機
- 再接続時は新しい Listener アドレスを Controller から通知

### 3.3 生存確認

KernelProcess が定期的（5秒間隔）に Input/Output プロセスのプロセス生存確認（`poll()`）を行い、
応答がない場合は子プロセスを再起動する。専用の制御イベントは使用しない。

## 4. メッセージ形式

### 4.1 InputMessage

Input Process から Kernel に送信されるユーザー入力メッセージ。Pydantic BaseModel として定義される。

```python
class InputMessage(BaseModel):
    msg_type: str    # "text" | "command" | "system"
    source: str      # "cli" | "tcp" など
    content: str     # 入力内容
    id: str          # UUID4先頭12文字
```

ワイヤー形式:
```json
{"msg_type": "text", "source": "cli", "content": "hello", "id": "abc123"}
```

### 4.2 OutputMessage

Kernel から Output Process に送信される応答メッセージ。

```python
class OutputMessage(BaseModel):
    msg_type: str        # "stream" | "response" | "proactive" | "anomaly"
    content: str         # 出力内容 (stream時はデルタ)
    id: str              # メッセージID (UUID4先頭12文字)
    correlation_id: str  # 対応する InputMessage のID（空文字列可）
    metadata: dict       # 補足情報（model名, doneフラグ等）
```

ワイヤー形式:
```json
{"msg_type": "stream", "content": "Hello ", "id": "xyz789", "correlation_id": "abc123", "metadata": {}}
```

### 4.3 内部イベント (EventBus)

EventBus は以下の Kernel 内部専用イベントのみを運搬する。IPC のワイヤー形式としては現れない。

| イベント | 説明 |
|----------|------|
| `TimerTick` | 定期タイマー (ProactiveEngine駆動用) |
| `AgentStateChangeEvent` | エージェント状態遷移 (busy, idle 等) |
| `MemoryUpdateEvent` | 記憶更新通知 |
| `AgentAnomalyEvent` | 異常検知通知 |

## 5. エラーハンドリング

| 状況 | Kernel 側の動作 | クライアント側の動作 |
|------|----------------|-------------------|
| 不正なイベント受信 | ログ出力 + 無視 | — |
| 接続断 (予期せず) | 該当スレッド終了 + ログ | 再接続試行 (指数バックオフ) |
| シリアライズエラー | ログ出力 + 接続断 | ログ出力 + 再接続 |
| 受信タイムアウト | — | 再接続試行 |

- KernelProcess が `subprocess.Popen` で Input/Output プロセスを起動・監視する。専用の制御 Pipe 経由のイベントは実装されていない。

## 6. 将来の拡張

### TCP/IP 対応

`AF_PIPE` → `AF_INET` に変更するだけで同一コードが動作する：

```python
# TCP 版
listener = multiprocessing.connection.Listener(
    address=("127.0.0.1", 9876),
    family="AF_INET",
    authkey=b"iris-secret",
)
```

### TLS 対応

`multiprocessing.connection.Listener` は直接 TLS をサポートしないため、
TCP 移行時に別途暗号化層を追加する必要がある。
当面は localhost 限定のため未対応。
