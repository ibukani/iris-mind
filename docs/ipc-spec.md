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
| `\\.\pipe\iris-kernel-output` | Kernel→Output | Kernel から Output Process へのイベント配信 |
| `\\.\pipe\iris-kernel-input` | Input→Kernel | Input Process から Kernel へのユーザー入力転送 |
| `\\.\pipe\iris-control` | 双方向 | Controller からのライフサイクル制御（シャットダウン、ヘルスチェック） |

Kernel は単一の Listener で全クライアント接続を受け付け、接続ごとにスレッドを割り当てる。

### 2.3 シリアライズ

JSON Lines 形式を使用する。`send_bytes()` / `recv_bytes()` でフレーミングする。

```python
# 送信
data = json.dumps(event.to_dict(), ensure_ascii=False)
conn.send_bytes(data.encode("utf-8"))

# 受信
raw = conn.recv_bytes().decode("utf-8")
event = Event.from_dict(json.loads(raw))
```

**ワイヤー形式** (他言語から読み書きする場合):

```
{ "type": "UserInputEvent", "content": "hello", "source": "cli", "timestamp": "...", "trace_id": "abc" }
```

**制約**:
- `send_bytes()` / `recv_bytes()` がフレーミングを内部処理
- 最大メッセージサイズはデフォルトで 32MB（要調整時は別途指定）

### 2.4 Replay ファイル形式

デバッグ用に、送受信されたイベントを JSONL 形式で記録する。

```jsonl
{"type": "UserInputEvent", "trace_id": "abc-123", "data": {"content": "hello", ...}}
{"type": "AgentStreamEvent", "trace_id": "abc-123", "data": {"delta": "Hello", ...}}
{"type": "AgentResponseEvent", "trace_id": "abc-123", "data": {"content": "...", ...}}
```

`ReplayableTransport` クラスがこの形式で記録する。再生用クラス（`ReplayTransport`）は未実装。

## 3. 接続ライフサイクル

### 3.1 起動シーケンス

```
Kernel Process:
  1. Listener 開始 (port 発表は stdout or 固定パイプ名)
  2. イベント購読開始
  3. クライアント接続待受 (非ブロッキング poll)

Input Process:
  1. Kernel の Listener に接続
  2. UserInputEvent の送信を開始

Output Process:
  1. Kernel の Listener に接続
  2. 受信ループ開始 (イベント受信 → 表示)
```

### 3.2 切断と再接続

- クライアント切断 → Kernel は該当スレッドをクリーンアップ
- Kernel 切断 → 全クライアントが `EOFError` を受信 → 再接続待機
- 再接続時は新しい Listener アドレスを Controller から通知

### 3.3 生存確認

Controller から定期的に `HeartbeatRequest` イベントを送信。
各プロセスは `HeartbeatResponse` で応答する。タイムアウト時は再起動。

## 4. イベント形式

### 4.1 基底イベント

```python
@dataclass
class Event:
    timestamp: datetime  # イベント生成時刻
    source: str          # 発生源 ("user_input" | "proactive" | "system" | "timer" | "input:*" | "output:*")
    trace_id: str        # UUID4 — 全プロセス横断追跡ID
```

### 4.2 Kernel → Output イベント

| イベント | フィールド | 説明 |
|----------|-----------|------|
| `AgentStreamEvent` | `delta: str`, `done: bool` | LLM ストリーミングトークン |
| `AgentResponseEvent` | `content: str`, `model: str` | 最終応答 |
| `ProactiveSpeechEvent` | `content: str`, `trigger_type: str`, `confidence: float` | 自発発話 |
| `AgentAnomalyEvent` | `anomaly_type: str`, `severity: str`, `detail: str` | 異常検知 |
| `AgentStateChangeEvent` | `previous_state: str`, `new_state: str` | 状態遷移通知 |

### 4.3 Input → Kernel イベント

| イベント | フィールド | 説明 |
|----------|-----------|------|
| `UserInputEvent` | `content: str`, `metadata: dict \| None` | ユーザー入力 |

### 4.4 制御イベント (Controller ↔ 全プロセス)

| イベント | フィールド | 説明 |
|----------|-----------|------|
| `HeartbeatRequest` | (なし) | 生存確認 |
| `HeartbeatResponse` | `pid: int`, `status: str` | 生存応答 |
| `ShutdownRequest` | `reason: str`, `graceful: bool` | シャットダウン指示 |
| `ShutdownAck` | `pid: int` | シャットダウン応答 |

## 5. エラーハンドリング

| 状況 | Kernel 側の動作 | クライアント側の動作 |
|------|----------------|-------------------|
| 不正なイベント受信 | ログ出力 + 無視 | — |
| 接続断 (予期せず) | 該当スレッド終了 + ログ | 再接続試行 (指数バックオフ) |
| シリアライズエラー | ログ出力 + 接続断 | ログ出力 + 再接続 |
| 受信タイムアウト | — | 再接続試行 |

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
