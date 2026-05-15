# IPC プロトコル仕様 v2.0

## 1. 概要

Iris Kernel は Named Pipe 経由で外部プロセスから制御可能な公開インターフェースを持つ。
Kernel は両方の Pipe で Listener（サーバー）として動作する。

## 2. 通信方式

### 2.1 Windows Named Pipes

`multiprocessing.connection` モジュールの `AF_PIPE` ファミリを使用する。

### 2.2 Pipe アドレス体系

| Pipe 名 | 方向 | 用途 |
|---------|------|------|
| `\\.\pipe\iris-kernel-input` | 外部→Kernel | 外部 Client から Kernel (Listener/InputManager) へのコマンド・テキスト入力 |
| `\\.\pipe\iris-kernel-output` | Kernel→外部 | Kernel (Listener/OutputManager) から外部 Client への出力送信 |

各 Pipe は独立した Listener を持つ。各 Manager は接続ごとにスレッドを割り当てる。

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

### 2.4 ワイヤー形式

送受信されるメッセージは JSON 形式で、`send_bytes()` / `recv_bytes()` でフレーミングする。

```json
{"msg_type": "text", "source": "cli", "content": "hello", "id": "abc123"}
{"msg_type": "stream", "content": "Hello ", "id": "xyz789", "correlation_id": "abc123", "metadata": {}}
{"msg_type": "response", "content": "...", "id": "...", "correlation_id": "abc123", "metadata": {"model": "qwen3.5:9b"}}
```

## 3. 接続ライフサイクル

### 3.1 起動シーケンス

```
Supervisor Process (main.py):
  1. KernelProcess.start() を呼び出し

Kernel Process:
  1. KernelFactory.build() — 全コンポーネント初期化
  2. OutputManager.start() — PipeServer(iris-kernel-output) 起動（Listener）
  3. InputManager.start() — PipeServer(iris-kernel-input) 起動 + 受付スレッド開始

外部 Client:
  1. 任意のタイミングで iris-kernel-input に Client 接続
  2. InputMessage の送信を開始
  3. iris-kernel-output に Client 接続して OutputMessage を受信
```

### 3.2 切断と再接続

- クライアント切断 → Kernel は該当スレッドをクリーンアップ
- Kernel 切断 → 全クライアントが `EOFError` を受信 → 再接続は Client 側の責務

## 4. メッセージ形式

### 4.1 InputMessage

外部 Client から Kernel に送信される制御メッセージ。Pydantic BaseModel として定義される。

#### コマンド一覧

| msg_type | content の例 | 説明 |
|----------|-------------|------|
| `"command"` | `/status` | Kernel の状態確認 |
| `"command"` | `/shutdown` | Kernel のグレースフルシャットダウン |
| `"command"` | `/sleep` | エージェント休止 |
| `"command"` | `/wakeup` | エージェント再開 |
| `"command"` | `/help` | コマンド一覧 |
| `"text"` | `"hello"` | テキスト入力（会話モード） |

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

Kernel から外部 Client に送信される応答メッセージ。

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

- Kernel は子プロセスを管理しない。外部 Client の接続・切断は Kernel の動作に影響しない。
- Supervisor (main.py) は管理コンソールで `/shutdown` を受け付け、Ctrl+C でも停止可能。
- Named Pipe 経由で `/shutdown` を受信すると KernelProcess がフラグを立て、Supervisor が検知してシャットダウンする。

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
