# Iris Cognitive Runtime Architecture (Current)

Iris は Cognitive Runtime Architecture v1.2.1 に基づく AI コンパニオン Runtime です。

EventBus/PluginManager を用いず、明示的な constructor injection と PipelineStep で構成されます。

## Runtime Flow

```text
CLI / main.py
→ Observation
→ CognitiveCycle (cognitive/cycle/)
   → SimplePerceptionStep (cognitive/perception/)
   → ResponseGenerationStep (cognitive/action/)   [action selection]
   → [その他 PipelineStep]
→ ActionPlan (contracts/)
→ ActionSafetyGate (safety/)
→ Presenter (presentation/)
→ PresentedOutput (contracts/)
→ OutputSafetyGate (safety/)
→ PresentedOutput
```

`IrisApp` (`iris/runtime/app.py`) が `process_observation()` で上記フローを実行します。

デフォルトの配線は `SimplePerceptionStep` → `ResponseGenerationStep` の 2 ステップ。
メモリ・感情・ポリシーステップ追加配線も用意されています (`wire_text_response_cognitive_cycle` 等)。

## Package Structure

```
iris/
├── core/              IDs, time, errors, Result 型
├── contracts/         ActionPlan, PresentedOutput, Observation 等の共有型
├── cognitive/
│   ├── cycle/          CognitiveCycle, PipelineStep protocol, FrameBuilder, CycleResult
│   ├── workspace/      WorkspaceFrame
│   ├── perception/     SimplePerceptionStep
│   ├── action/         ResponseGenerationStep (action selection)
│   ├── affect/         AppraisalStep, RelationshipStep
│   ├── memory/         MemoryRetrievalStep
│   └── policy/         PolicyInhibitionStep
├── presentation/       Presenter protocol → SimplePresenter
├── safety/             ActionSafetyGate, OutputSafetyGate (protocol + AllowAll)
├── features/           FeatureDefinition, LearningHook, proactive_talk/
├── adapters/           LLM (fake, openai), memory store, app_gateway protocol
└── runtime/             IrisApp 本体, CLI entrypoint, wiring/
    └── wiring/         constructor injection のみ (app, cognitive, llm, memory, etc.)
```

## Layer Dependency Direction

許可:

```text
contracts → core
cognitive → contracts, core
presentation → contracts, core
safety → contracts, core
adapters → contracts, core
features → contracts, cognitive (PipelineStep protocol), core
runtime → 全層
```

禁止:

```text
cognitive → adapters, runtime, features
contracts → cognitive, adapters, runtime
features → adapters (FeatureDefinition で例外あり)
adapters → cognitive (LLM adapter → LLMClient protocol で例外あり)
```

`runtime` だけが全体を知ってよい。

## Wiring Rules

- `runtime/wiring/` は constructor injection のみ。
- `resolve()`, `get_service()`, `locate()` の使用禁止。
- wiring ファイルにドメインロジック・認知ロジックを書かない。

## 禁止パターン

- EventBus による CognitiveCycle 主制御
- PluginManager compatibility layer
- Service locator / global registry / hidden DI container
- `action: str` dispatcher 分岐
- `dict[str, Any]` / `dict[str, object]` による層間コンテキスト
- WorkspaceFrame の可変 (mutable) 設計
- PipelineStep による Frame 直接ミューテーション
- CognitiveCycle 内での adapter 呼び出し

## 機能追加

1. `iris/features/<name>/` に FeatureDefinition を作成
2. 必要なら PipelineStep, ObservationSource, LearningHook を定義
3. `iris/runtime/wiring/features.py` で wiring
4. アーキテクチャテストが通ることを確認

## 現状のスコープ

- text-only 1 ターン会話
- FakeLLM デフォルト (OpenAI 切替可)
- メモリ検索・感情評価・関係性・ポリシー抑制の PipelineStep は実装済み (配線選択可能)
- 永続ストレバックエンドは未実装 (InMemoryStore のみ)
- 外部アプリ連携 (Discord, Voice, Twitch) は未実装
- AppGateway は Protocol のみ定義 (将来の外部アプリ用)

## 関連文書

- 完全版設計書 (archived): `docs/archive/cognitive-runtime-v1.2.1.md`
- レガシー削除記録: `docs/archive/legacy-removal-summary.md`
- 開発ガイド: `docs/development/testing.md`
- AIエージェントガイドライン: `docs/development/agent-guidelines.md`
