# How Iris Works

> Iris の全機能をコードを交えずに説明する。
> 各機能の詳細は `docs/how-it-works/` 以下の個別文書を参照。

```mermaid
flowchart LR
    EB["Global EventBus"] --- IO["IO層"]
    EB --- MEM["Memory層"]
    EB --- AG["Agency層"]
    EB --- KRN["Kernel層"]
    IO <--> CLI["Client"]
    AG --- LLM["LLM基盤"]
```

## 文書一覧

| 文書 | 内容 |
|------|------|
| [EventBus / 層間通信](how-it-works/01-eventbus.md) | 購読・発行・シリアライズ・配送保証 |
| [記憶システム](how-it-works/02-memory-system.md) | 感覚→短期→長期、GoalStore |
| [意思決定](how-it-works/05-decision-making.md) | PlanningManager・InputReady振分 |
| [自発発話スコアリング](how-it-works/06-proactive-scoring.md) | 全因子の計算式と重み |
| [実行パイプライン](how-it-works/08-execution-pipeline.md) | FlowExecutor・Workflow・ツールループ |
| [モデルルーティング](how-it-works/11-model-routing.md) | LLMBridge・PriorityLock・provider切替 |
