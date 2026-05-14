# AgentKernel 設計仕様

## 概要

AgentKernel は Iris カーネルの状態管理・イベント統括・Tier3 異常検知を担当する。
エントリポイントは IrisController が担い、AgentKernel はその一部として動作する。

## 責務

1. **ライフサイクル管理** — `startup()` / `shutdown()` でカーネルの開始・停止を統括
2. **TimerTick 発行** — バックグラウンドスレッドで定期発行（ProactiveEngine の駆動源）
3. **イベントルーティング** — 購読したイベントを適切なコンポーネントに配送
4. **Tier3 異常検知** — 自発発話の頻度超過・悪循環パターンを検出し警告
5. **状態タイムアウト監視** — 各状態の滞在時間超過を検出し IDLE に復帰

## クラス構成

```
AgentKernel
├── startup()
│   ├── subscribe(UserInputEvent)      → _on_user_input()
│   ├── subscribe(ProactiveSpeechEvent) → _on_proactive_speech()
│   ├── subscribe(AgentStateChangeEvent) → _on_state_change()
│   ├── subscribe(AgentResponseEvent)   → _on_agent_response()
│   └── timer thread → publish TimerTick
├── shutdown()
│   └── stop timer thread
├── _on_user_input(event)
│   ├── state check (IDLE only)
│   ├── transition to PROCESSING
│   ├── ProactiveEngine.notify_user_activity()
│   ├── MemoryManager.add_episodic()
│   └── (IDLE 遷移は _on_agent_response が担当)
├── _on_agent_response(event)
│   ├── MemoryManager.add_episodic()
│   └── transition to IDLE
├── _on_proactive_speech(event)
│   ├── MemoryManager.add_episodic()
│   └── AnomalyDetector.record_speech() + check_suppression_health()
└── _on_state_change(event)
    └── logging

AnomalyDetector (Tier3)
├── record_speech() → list[str]
│   └── 直近5分間のスライディングウィンドウで頻度超過検出
└── check_suppression_health(status) → list[dict]
    ├── confirmation_mode → dict(type, severity, detail)
    ├── high_ignore_rate → dict(type, severity, detail)
    └── negative_mood → dict(type, severity, detail)
```

## イベントフロー

```
[TimerTick 発行 (check_interval_sec ごと)]
    ├── → ProactiveEngine._on_timer_tick() （EventBus 経由で自動配信）
    │      └── スコアリング → 発話 → ProactiveSpeechEvent
    └── → AgentKernel._on_timer（check_timeout 実行）

[UserInputEvent 受信]
    └── → AgentKernel._on_user_input()
           ├── 状態遷移（IDLE → PROCESSING）
           ├── ProactiveEngine にユーザー活動を通知
           └── 入力をエピソード記憶に記録
    → ConversationService._on_user_input()
           └── LLM 応答 → AgentResponseEvent
    → AgentKernel._on_agent_response()
           ├── 応答をエピソード記憶に記録
           └── 状態遷移（PROCESSING → IDLE）

[ProactiveSpeechEvent 受信]
    └── → AgentKernel._on_proactive_speech()
           ├── 発話をエピソード記憶に記録
           └── AnomalyDetector で異常検知 + 健全性チェック
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
├── EventBus（イベント発行・購読）
├── AgentStateManager（状態遷移・タイムアウト監視）
├── ProactiveEngine（ユーザー活動通知・抑制状態取得）
├── MemoryManager（エピソード記憶への記録）
└── ProactiveConfig（チェック間隔等の設定値）
```
