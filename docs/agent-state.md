# AgentState 状態遷移設計書

## 状態一覧

| 状態 | 定数値 | 説明 |
|------|--------|------|
| IDLE | `idle` | 待機中。トリガー監視・自発発話の起点 |
| PROCESSING | `processing` | ユーザー入力を処理中。LLM応答・Tool呼び出し・ストリーミング |
| PROACTIVE | `proactive` | 自発発話を実行中。抑制ロジックのクールダウン開始 |
| REFLECTING | `reflecting` | Reflexionによる自己反省処理中。PersonaProfile更新 |
| THINKING | `thinking` | 思考モード（Chain-of-Thought）推論中 |
| SLEEPING | `sleeping` | 一時休止。全イベント抑制（緊急イベントを除く） |

## 状態遷移図

```
                 ┌──────────────┐
                 │              │ TimerTick + スコア>閾値
                 │  ┌─────┐     │
                 ▼  │     │     ▼
              ┌─────┐    ┌──────────┐     ┌──────────┐     ┌──────────┐
  ──────────► │ IDLE │───►│PROCESSING│────►│REFLECTING│     │THINKING  │
  起動/復帰    └──┬──┘    └──────────┘     └──────────┘     └──────────┘
                 │         ▲   │                            │
                 │         │   │ 正常完了                    │ 推論完了
                 │         │   │ /timeout                    │ /ユーザー入力
                 │         │   │ /error                      ▼
                 │    /sleep│   │                     ┌──────────┐
                 │         │   ├─────────────────────►│  IDLE   │
                 │         │   │                      └──────────┘
                 │         ▼   │
                 │    ┌──────────┐    ┌───────────┐
                 │    │PROACTIVE │───►│SLEEPING   │
                 │    └──────────┘    └─────┬─────┘
                 │         ▲                │
                 │         │                │ /wakeup or
                 │         │                │ timeout
                 │    /sleep│                │
                 │         │                │
                 └─────────┘────────────────┘
```

## 遷移テーブル

| From \ To | IDLE | PROCESSING | PROACTIVE | REFLECTING | THINKING | SLEEPING |
|-----------|------|-----------|-----------|-----------|---------|---------|
| **IDLE** | ○ | ○ | ○ | × | ○ | ○ |
| **PROCESSING** | ○ | ○ | × | ○ | × | ○ |
| **PROACTIVE** | ○ | × | × | × | × | ○ |
| **REFLECTING** | ○ | ○ | × | × | × | × |
| **THINKING** | ○ | ○ | × | × | × | × |
| **SLEEPING** | ○ | × | × | × | × | × |

※ ○ = 許可, × = 禁止

## 各状態の詳細

### IDLE（待機中）
```
入口アクション:
  - ProactiveEngine のトリガー監視を開始
  - TimerTick リスナーをアクティブ化

イベント処理:
  - TimerTick → ProactiveEngine.check_trigger()
    → スコア >= threshold → PROACTIVE 遷移
  - UserInputEvent → PROCESSING 遷移
  - /sleep → SLEEPING 遷移
  - /think → THINKING 遷移

出口条件:
  - 上記イベントのいずれかを受信
```

### PROCESSING（処理中）
```
入口アクション:
  - タイムアウト計測開始（デフォルト 60秒）
  - ユーザー入力バッファリング開始

イベント処理:
  - 新規ユーザー入力 → キューにバッファ（処理完了後に再評価）
  - 正常完了 → IDLE 遷移、応答イベント発行
  - Quick Reflection 条件達成 → REFLECTING 遷移
  - /sleep → SLEEPING 遷移（処理中断）

タイムアウト:
  - 60秒超過 → エラー応答 → IDLE 遷移
```

### PROACTIVE（自発発話中）
```
入口アクション:
  - クールダウンタイマー開始
  - 無視検出カウンターリセット

イベント処理:
  - 発話完了 → 3秒クールダウン → IDLE 遷移
  - ユーザー発話検出 → 即座に IDLE 遷移（発話中断）
  - ユーザー無反応（60秒）→ neutral タグ付き記録 → IDLE

クールダウン:
  - 発話後 min_interval_sec (30秒) は再発話しない
```

### REFLECTING（自己反省中）
```
入口アクション:
  - 会話履歴スナップショット取得

イベント処理:
  - Reflexion 完了 → IDLE 遷移
  - 高優先度ユーザー入力 → 一時中断 → PROCESSING → 終了後に再開
```

### THINKING（思考モード）
```
入口アクション:
  - CoT 推論開始

イベント処理:
  - 推論完了 → 結果通知（任意）→ IDLE
  - ユーザー入力 → PROCESSING（推論結果を活用）
```

### SLEEPING（一時休止）
```
入口アクション:
  - cooldown_expiry = now + cooldown_duration
  - 全イベントバッファリング開始
  - ProactiveEngine 完全停止

イベント処理:
  - 全イベント → バッファに保持（処理しない）
  - cooldown 経過 → IDLE 遷移、バッファ処理再開
  - /wakeup → 即座に IDLE 遷移
  - 緊急イベント（内部エラー等）→ 一時復帰 → IDLE
```

## タイムアウト設定

| 状態 | タイムアウト | 動作 |
|------|------------|------|
| PROCESSING | 60秒 | エラー応答 → IDLE |
| PROACTIVE | 30秒 | 強制終了 → IDLE |
| REFLECTING | 15秒 | 中断 → IDLE |
| THINKING | 120秒 | 中断 → IDLE |
| SLEEPING | ∞ | /wakeup or cooldown 終了のみ |
| IDLE | ∞ | TimerTick によるトリガーのみ |

## 優先度ルール（イベント競合解決）

同時に複数イベントが到着した場合の処理優先順位：

1. **UserInputEvent** — 最優先、常に即処理
2. **システムコマンド**（/sleep, /wakeup 等）— 即時処理
3. **TimerTick** — 状態が IDLE の場合のみ評価
4. **ProactiveSpeechEvent** — PROCESSING/PROACTIVE 中はキューイング
