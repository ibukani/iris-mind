# 3-Process Migration Roadmap

> **この文書のライフサイクル**: Phase 0-4 の移行完了後、Phase 5 でこの文書自体を削除する。
> 移行が完了した Iris の最終アーキテクチャについては `docs/architecture.md` を参照すること。

## 目標

Iris を単一プロセス → 3プロセス（Input / Kernel / Output）に段階的に移行する。

## Phase 0 — 基盤整備（EventBus Protocol + シリアライズ）

**目的**: プロセス間通信の API を定義する。既存コードは変更せず動作し続ける。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `iris/kernel/event_bus.py` | 編集 | `EventBusProtocol` を追加。既存 `EventBus` はその実装として継続 |
| `iris/kernel/event.py` | **新規** | 全イベントクラスを `event_bus.py` から抽出 + `trace_id` 追加 + `to_dict()` / `from_dict()` |
| `iris/kernel/ipc.py` | **新規** | `PipeServer` / `PipeClient` + `ReplayableTransport` |
| `iris/kernel/__init__.py` | 編集 | 必要に応じて公開API追加 |
| `tests/` | 編集 | Protocol ベースのテスト + IPC の単体テスト（+15 tests） |

### 完了条件

- `pytest tests/ -q` 全179テスト通過（変更なし）
- `EventBusProtocol` が定義され、既存 `EventBus` がそれを実装
- イベントに `trace_id` が追加され、伝搬することのテスト完了
- `ReplayableTransport` がイベントを JSONL に記録・再生可能

### リスク: 低

API の追加のみで既存コードの変更が最小限。後方互換性を維持。

---

## Phase 1 — Output Process 分離

**目的**: 表示処理を Kernel から切り離す。Output は stateless なので最も分離しやすい。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `adapters/cli/output_main.py` | **新規** | Output Process エントリポイント。Pipe 読込 → Rich 表示 |
| `adapters/cli/renderer.py` | **新規** | CLIAdapter から表示ロジックを抽出（stream, panel, proactive, anomaly表示） |
| `adapters/cli/__init__.py` | 編集 | パッケージ登録 |
| `iris/kernel/ipc_output.py` | **新規** | OutputBridge: EventBus 購読 → Pipe 送信の中継 |
| `iris/kernel/event_bus.py` | 編集 | 必要に応じて IPC 対応追加 |
| `iris/kernel/factory.py` | 編集 | OutputBridge の生成を追加 |
| `main.py` | 編集 | `--output-separate` オプション追加 |

### データフロー

```
Kernel Process:
  ConversationService → EventBus.publish(AgentStreamEvent)
    → OutputBridge._on_stream_token()
      → PipeServer.broadcast(AgentStreamEvent(...))

Output Process:
  PipeClient.recv() → AgentStreamEvent
    → Renderer.on_stream_token(event)
      → Rich Live 更新
```

### フォールバック

単一プロセスモード（`python main.py`）は今まで通り動作。
移行中は両方のモードを並行維持。

### 完了条件

- `python main.py --output-separate` で Output が別プロセスとして起動
- 会話が通常通り動作（表示は別プロセスから）
- Output Process を Kill → Kernel が継続動作することを確認
- `pytest tests/ -q` 通過

### リスク: 中

新規プロセスの起動・停止・エラーハンドリングの導入が必要。

---

## Phase 2 — Input Process 分離

**目的**: 入力処理を Kernel から切り離す。複数入力ソースの同時接続が可能に。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `adapters/cli/input_main.py` | **新規** | Input Process エントリポイント。`input()` → Pipe 送信 |
| `adapters/cli/server.py` | **削除** | 機能を input_main / output_main / renderer / ProactiveResponseTracker に分割完了 |
| `iris/kernel/proactive_response_tracker.py` | **新規** | CLIAdapter._check_proactive_response を移植。Kernel 内で動作 |
| `iris/kernel/ipc_input.py` | **新規** | InputBridge: Pipe 受信 → EventBus publish |
| `main.py` | 編集 | `--separate` オプション追加（3プロセス起動） |
| `adapters/cli/__init__.py` | 編集 | パッケージ構成更新 |

### Proactive 応答追跡の移動

**Before** (Phase 1 までの Input Process):

```python
# CLIAdapter: Input + Proactive応答評価 の両方を持っている
class CLIAdapter:
    def _check_proactive_response(self, text):
        # 直近の自発発話に対するユーザー反応を評価
```

**After** (Phase 2):

```python
# ProactiveResponseTracker: Kernel 内の独立コンポーネント
class ProactiveResponseTracker:
    def __init__(self, proactive, event_bus):
        event_bus.subscribe("ProactiveSpeechEvent", self._on_proactive)
        event_bus.subscribe("UserInputEvent", self._on_user_input)

    def _on_user_input(self, event):
        # 保留中の Proactive 応答があれば評価
        if self._pending and time.time() - self._pending <= 60:
            self._evaluate_response(event.content)
```

### データフロー

```
Input Process:
  input(">>> ") → PipeClient.send(UserInputEvent(content=text))

Kernel Process:
  PipeServer.recv() → InputBridge → EventBus.publish(UserInputEvent)
    → ProactiveResponseTracker._on_user_input()  # 応答評価
    → ConversationService._on_user_input()        # LLM処理
    → ProactiveEngine.notify_user_activity()      # 抑制状態更新

Output Process:
  (Phase 1 と同じ)
```

### 完了条件

- `python main.py --separate` で3プロセス起動、通常通りの会話
- 2つの Input Process を同時起動 → 両方の入力を受け付ける
- Proactive 応答評価が Kernel 内で正しく動作
- `/sleep`, `/wakeup` 等のコマンドが全 Input で動作
- `pytest tests/ -q` 通過

### リスク: 中

Input Process からのコマンド処理（`/help` 等）と Kernel 内の Proactive 応答追跡の統合が要設計。

---

## Phase 3 — Controller プロセス導入

**目的**: 3プロセスの起動・監視・停止を一元管理。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `iris/kernel/controller.py` | **新規** | 3プロセス起動 + 死活監視 + グレースフルシャットダウン |
| `main.py` | 編集 | Controller を起動するだけの薄いエントリポイントに |

### Controller 責務

```
main.py → Controller.launch()
  ├── KernelProcess.spawn()
  ├── InputProcess.spawn("cli")
  ├── OutputProcess.spawn("cli")
  └── 全プロセスのヘルスチェックループ (5秒間隔)
```

### 障害復旧シナリオ

| 障害 | Controller の動作 |
|------|------------------|
| Output Process がクラッシュ | Kernel は継続 → Controller が Output を再起動 |
| Input Process がクラッシュ | Kernel + Output は継続 → 再接続に備える |
| Kernel Process がクラッシュ | 全プロセス終了 → 起動し直し（状態は永続化済み） |

### 完了条件

- `python main.py` で Controller が3プロセスを起動
- Output Process を強制終了 → Controller が検知、ログ出力
- `Ctrl+C` で全プロセスがグレースフルシャットダウン
- `pytest tests/ -q` 通過

### リスク: 中

プロセス管理（spawn / signal / cleanup）の実装が必要。

---

## Phase 4 — マルチ入力ソース対応

**目的**: 複数の Input / Output を同時運用。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `iris/kernel/ipc.py` | 編集 | 複数接続管理の最適化 |
| 各種 Input Adapter 追加 | **新規** | WebSocket 等 |

### 想定ユースケース

```
Input A: CLI (キーボード) ────┐
Input B: WebSocket API ───────┤
Input C: Discord Bot ─────────┤
                              │
                    Kernel Process
                              │
Output A: CLI (Rich表示) ─────┤
Output B: WebSocket ─────────┤
Output C: ログファイル ──────┘
```

### 完了条件

- 2種類以上の Input が同時に接続し、それぞれの入力が処理される
- 全 Output にイベントがブロードキャストされる

### リスク: 低

Phase 0-3 の延長線上。新規 Input/Output アダプターの追加のみ。

---

## Phase 5 — v0.2 名残りの整理

**目的**: 3-Process 移行完了後、v0.2 時代のコード・ドキュメントの名残を一掃する。

### 変更内容

| ファイル | 変更種別 | 内容 |
|----------|---------|------|
| `docs/migration-roadmap.md` | **削除** | 移行完了後は不要な文書 |
| `adapters/cli/server.py` | 削除済 (Phase 2) | 確認 |
| `adapters/cli/__init__.py` | 編集 | 不要なエクスポート削除 |
| `main.py` | 編集 | `--output-separate` 等の移行用フラグ削除、Controller 起動のみに |
| 全ソース | 確認 | docstring 中の "v0.2" 参照を "v0.3" に更新 |
| `docs/*.md` | 確認 | 古いアーキテクチャ図・参照の更新漏れチェック |
| `docs/README.md` | 編集 | migration-roadmap.md へのリンク削除 |

### 削除対象の具体例

移行完了後に探すべき v0.2 の痕跡:

- `CLIAdapter` クラス名・参照（input_main / output_main / renderer に分割完了）
- docstring 中の `v0.2` 記述
- 古いアーキテクチャ図（単一プロセスの箱と矢印）
- 使用されなくなった import / 定数 / 関数
- 単一プロセス用のフォールバックコードパス

### 完了条件

- `docs/migration-roadmap.md` が削除されている
- ソース内に `# v0.2` コメント / docstring がない
- すべてのドキュメントが v0.3 アーキテクチャを正しく参照
- `pytest tests/ -q` 全テスト通過

### リスク: 極低

削除とリネームのみ。新規ロジックの追加なし。

---

## 全 Phase の変更ファイル総数

| Phase | 新規ファイル | 変更ファイル | 削除ファイル | テスト増加数 |
|-------|-------------|-------------|-------------|-------------|
| Phase 0 | 2 | 1 | 0 | +15 |
| Phase 1 | 3 | 3 | 0 | +20 |
| Phase 2 | 3 | 2 | 1 | +20 |
| Phase 3 | 1 | 1 | 0 | +10 |
| Phase 4 | 0 | 1 | 0 | +5 |
| Phase 5 | 0 | 3 | 1 | 0 |
| **合計** | **9** | **11** | **2** | **+70** |

既存テスト 179 件は全 Phase を通して変更なしで通過し続ける。
