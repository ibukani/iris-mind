# AgentKernel 設計仕様

## 概要

AgentKernel は Iris カーネルの状態管理・イベント統括・Tier3 異常検知を担当する。
エントリポイントは KernelProcess が担い、AgentKernel はその一部として動作する。

## 責務

1. **ライフサイクル管理** — `startup()` / `shutdown()` でカーネルの開始・停止を統括
2. **TimerTick 発行** — バックグラウンドスレッドで定期発行（ProactiveEngine の駆動源）
3. **InputMessage 処理** — InputManager からの入力を ConversationService/ProactiveEngine へ配送
4. **Tier3 異常検知** — 自発発話の頻度超過・悪循環パターンを検出し警告
5. **状態タイムアウト監視** — 各状態の滞在時間超過を検出し IDLE に復帰

## クラス構成

```
AgentKernel
├── startup()
│   ├── subscribe(AgentStateChangeEvent) → _on_state_change()
│   └── timer thread → publish TimerTick
├── shutdown()
│   └── stop timer thread
├── on_input(msg: InputMessage)
│   ├── state check (IDLE only)
│   ├── transition to PROCESSING
│   ├── ProactiveEngine.notify_user_activity()
│   ├── MemoryManager.add_episodic()
│   ├── ConversationService.process_input(msg.content, on_complete)
│   │   └─ on_complete → transition to IDLE
│   └── ProactiveEngine.notify_user_activity() (再度)
├── on_response_complete()
│   ├── MemoryManager.add_episodic()
│   └── transition to IDLE
├── on_proactive_speech(content)
│   ├── MemoryManager.add_episodic()
│   ├── AnomalyDetector.record_speech() + publish AgentAnomalyEvent
│   └── AnomalyDetector.check_suppression_health() + publish AgentAnomalyEvent
├── _on_state_change(event)
│   └── logging
├── evaluate_proactive_request(scores, confidence, trigger_type) → bool
│   ├── AnomalyDetector.check_frequency() — 頻度超過チェック
│   ├── AnomalyDetector.check_suppression_health() — 抑制状態チェック
│   └── AgentStateManager.is_idle() — 状態チェック
│   └── 全条件を満たせば True（Tier2 発話承認）
└── _start_timer()
    └── TimerTick 発行 + AgentStateManager.check_timeout() 実行（ループ内）

AnomalyDetector (Tier3)
├── record_speech() → list[str]
│   └── 直近5分間のスライディングウィンドウで頻度超過検出（副作用あり）
├── check_frequency() → list[str]
│   └── 現在の頻度超過確認（副作用なし、evaluate_proactive_request から呼ばれる）
└── check_suppression_health(status) → list[dict]
    ├── confirmation_mode → dict(type, severity, detail)
    ├── high_ignore_rate → dict(type, severity, detail)
    └── negative_mood → dict(type, severity, detail)
```

## イベントフロー

EventBus は Kernel 内部専用。I/O は InputMessage/OutputMessage (Pydantic) で通信する。

```
[TimerTick 発行 (check_interval_sec ごと)]
    ├── → ProactiveEngine._on_timer_tick() （EventBus 経由で自動配信）
    │      └── スコアリング → Tier2判定 → 発話 → on_proactive_speech()
    └── → AgentKernel._start_timer ループ内で AgentStateManager.check_timeout() 実行

[InputMessage 受信 (from InputManager)]
    └── → AgentKernel.on_input(msg)
           ├── 状態遷移（IDLE → PROCESSING）
           ├── ProactiveEngine にユーザー活動を通知
           ├── 入力をエピソード記憶に記録
           ├── ConversationService.process_input() → LLM 応答
           └── on_response_complete → PROCCESSING → IDLE

[ProactiveEngine 発話決定]
    └── → AgentKernel.on_proactive_speech(content)
           ├── 発話をエピソード記憶に記録
           ├── OutputManager.send(proactive, ...)
           ├── AnomalyDetector.record_speech() → 頻度超過時はクールダウン設定
           └── AnomalyDetector.check_suppression_health() → 異常を AgentAnomalyEvent で通知
```

## Tier3 異常検知ルール

| ルール | 条件 | 深刻度 | アクション |
|--------|------|--------|-----------|
| 頻度超過 | 直近5分に5回以上の自発発話 | warning | ログ警告 + 300秒クールダウン |
| 無視蓄積 | consecutive_ignores >= 3 | warning | ログ警告 |
| confirmation_mode | confirmation_mode == True | warning | ログ警告 |
| ネガティブ感情 | negative_mood_score >= 0.7 | info | 情報ログ |

## 依存関係

```
AgentKernel
├── EventBus（内部イベント発行・購読）
├── AgentStateManager（状態遷移・タイムアウト監視）
├── ProactiveEngine（ユーザー活動通知・抑制状態取得）
├── MemoryManager（エピソード記憶への記録）
├── ConversationService（ユーザー入力の処理委譲）
├── OutputManager（自発発話の送信）
└── ProactiveConfig（チェック間隔等の設定値）
```
