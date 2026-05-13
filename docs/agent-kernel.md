# AgentKernel 設計仕様

## 概要

AgentKernel は Iris カーネルのエントリポイント。EventBus によるイベント駆動を前提に、
ライフサイクル管理、イベントルーティング、Tier3 異常検知を担当する。

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
│   └── timer thread → publish TimerTick
├── shutdown()
│   └── stop timer thread
├── _on_user_input(event)
│   ├── state check (IDLE or PROCESSING)
│   ├── transition to PROCESSING
│   ├── ProactiveEngine.notify_user_activity()
│   ├── MemoryManager.add_episodic()
│   └── transition to IDLE
├── _on_proactive_speech(event)
│   ├── MemoryManager.add_episodic()
│   └── AnomalyDetector.record_speech() + check_suppression_health()
└── _on_state_change(event)
    └── logging

AnomalyDetector (Tier3)
├── record_speech() → list[flag]
│   └── 直近5分間のスライディングウィンドウで頻度超過検出
└── check_suppression_health(status) → list[issue]
    ├── confirmation_mode → warning
    ├── high_ignore_rate → warning
    └── negative_mood → info
```

## イベントフロー

```
[TimerTick 発行 (check_interval_sec ごと)]
    ├── → ProactiveEngine._on_timer_tick() （EventBus 経由で自動配信）
    │      └── スコアリング → 発話 → ProactiveSpeechEvent
    └── → AgentKernel._on_timer（check_timeout 実行）

[UserInputEvent 受信]
    └── → AgentKernel._on_user_input()
           ├── 状態遷移（IDLE → PROCESSING → IDLE）
           ├── ProactiveEngine にユーザー活動を通知
           └── 入力をエピソード記憶に記録
           （会話応答は将来 ConversationService が担当）

[ProactiveSpeechEvent 受信]
    └── → AgentKernel._on_proactive_speech()
           ├── 発話をエピソード記憶に記録
           └── AnomalyDetector で異常検知 + 健全性チェック
```

## Tier3 異常検知ルール

| ルール | 条件 | 深刻度 | アクション |
|--------|------|--------|-----------|
| 頻度超過 | 直近5分に5回以上の自発発話 | warning | ログ警告 |
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
