# ADR 002: Agency Layer Architecture — 神経科学ベースの層分割

## ステータス

Accepted (2026-05-17)

## コンテキスト

v0.3 の `iris/kernel/` は以下をすべて内包している:

- プロセス管理 (KernelProcess, Supervisor)
- 入出力 (TcpListener, SessionManager, Authenticator)
- イベントルーティング (EventBus)
- 会話オーケストレーション (ConversationService)
- LLM パイプライン・ツール実行 (LLMPipeline, ToolExecutionEngine)
- 自発発話 (ProactiveEngine)
- 記憶管理 (MemoryManager)
- 自己反省 (Reflexion, ReflexionManager)
- コンテキスト圧縮 (ContextManager)
- 状態管理 (AgentStateManager)
- コマンド処理 (CommandHandler)

問題点:
- kernel フォルダに全サービスが詰め込まれ責務が肥大化
- コンポーネント間の依存関係がフラットで、変更が全体に波及しやすい
- 脳科学の構造（前頭前野・大脳基底核・海馬・視床など）との対応がつかず、設計の意図が伝わりにくい

## 決定

以下の層分割を行い、`iris/kernel/` を純粋なプロセス管理と DI コンテナに縮退させる。

### 層定義

| 層 | 脳科学対応 | 責務 |
|----|-----------|------|
| `iris/kernel/` | 脳幹 + 視床下部 | プロセスライフサイクル、ヘルスモニタリング、状態集約、コマンド処理、DI |
| `iris/io/` | 視床 | 入出力中継（TCP トランスポート、セッション管理、認証） |
| `iris/memory/` | 感覚野 + 海馬 + 皮質記憶系 | 感覚バッファ、エピソード記憶、意味記憶、記憶整理（Reflexion）、コンテキスト圧縮 |
| `iris/agency/` | 前頭前野 + 大脳基底核 + 運動野 | 意思決定（planning）と行動実行（execution） |
| `iris/event/` | 神経路（白質） | 層をまたぐグローバルイベントバス（kernel から分離） |
| `iris/llm/` | — | LLM インフラ（変更なし） |
| `iris/capabilities/` | — | ツール実装（変更なし） |
| `iris/tools/` | — | @tool, ToolRegistry（変更なし） |

### イベント一覧（グローバル EventBus）

| イベント | 送信元 → 受信先 | 説明 |
|----------|----------------|------|
| `InputReceived(msg)` | IO → Memory | 生入力到着 |
| `InputReady(content)` | Memory → Agency | 入力確定→判断依頼 |
| `OutputRequest(output)` | Agency → IO | 出力要求 |
| `OutputSent(result)` | IO → Memory | 出力完了通知 |
| `Completed(session_id)` | Agency → Memory | 処理完了→記憶へ |
| `TimerTick` | Kernel → 全層 | 定期鼓動 |
| `CommandRequest(cmd)` | IO → Kernel | 外部コマンド |

### Agency 内部通信

`iris/agency/bus.py` に内部 EventBus を持ち、planning ↔ execution 間の通信に使う。

| イベント | 送信元 → 受信先 | 説明 |
|----------|----------------|------|
| `PlanDecided(plan)` | Planning → Execution | 意思決定→実行依頼 |
| `ExecutionResult(result)` | Execution → Planning | 実行結果→フィードバック |
| `ExecutionFeedback(query)` | Execution → Planning | 実行中の問い合わせ |

### 各層の構造（Manager + Plugins）

各層は `Manager`（オーケストレーション）を置き、個別機能は plugin として追加される。Manager は EventBus との接続と層内コンポーネントの呼び出し順序のみを担当する。

## 影響

### ポジティブ

- 責務が明確に分離され、変更の影響範囲が局所化される
- 脳科学マッピングにより設計意図が伝わりやすい
- EventBus が層間結合を疎にする
- 各層 Manager + Plugin 構造で拡張性が高い
- 記憶整理（Reflexion）が Memory 内部で完結し、Planning は整理済みの記憶のみ参照

### ネガティブ

- 大規模リファクタリング（一部機能は一時削除）
- Factory（DI）が複雑化する可能性
- 層間のループ依存（Memory→Agency→Memory など）が EventBus で隠蔽されるため、トレーシングが難しくなる可能性

## 移行方針

1. 新ディレクトリ構造 + EventBus 移動（Phase 1）
2. 最小ループを通す（Phase 2）: エピソード記憶のみ + 最小 Planning + LLM Pipeline
3. 以降のフェーズで削除した機能を再実装

Phase 2 では以下を**一時的に削除**:
- ProactiveEngine（自発発話）
- Reflexion + ReflexionManager（自己反省）
- 準同期入力区別（converse_text / dispatch_text の統合）
- CommandHandler（ただし `iris/kernel/commands/` として移植）
- SemanticStore / VectorStore（ChromaDB）
- AgentsMdStore / PersonaProfile
- AnomalyDetector

## 参考

- docs/v2/architecture.md（層別詳細設計）
- docs/v2/memory-layer.md
- docs/v2/agency-layer.md
- docs/v2/kernel-layer.md
- docs/v2/io-layer.md
