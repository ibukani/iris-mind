---
name: iris-visualize
description: |
  Irisプロジェクトの脳科学層アーキテクチャおよびEventBusシーケンス図の可視化、Mermaidシンタックス検証、SVG/ASCIIレンダリングを行うスキル。

  使用タイミング:
  1. 新規モジュールやレイヤーの構成図、シーケンス図を作成/更新するとき
  2. Mermaidの記述エラーがないかシンタックス検証を行うとき
  3. MermaidコードからSVGまたはASCIIアートを生成するとき
---

# Iris Visualize Skill

Irisの層アーキテクチャやEventBusによる疎結合設計を正しく表現し、Mermaidの構文チェックおよびレンダリングを行う。

---

## 1. Mermaidシンタックス検証方法

記述したMermaidコードに構文エラーがないか検証する。

### A. CLIによる検証 (最速・推奨)
`npx` を使って構文エラーがないかを検証する（Windows環境では `NUL` 出力先を使用して画像出力をスキップする）。
```powershell
npx -y @mermaid-js/mermaid-cli -i <対象ファイル.mmd> -o temp.svg
# 検証完了後に生成された temp.svg は削除してよい。
```
*※ 正常終了（終了コード0）なら構文は正しい。エラーがある場合はエラー箇所と詳細が出力される。*

### B. レンダリングによる検証
既存のレンダリングスクリプトを実行し、エラーが発生しないか確認する。
```powershell
node scripts/render.mjs --input <対象ファイル.mmd>
```

---

## 2. レンダリングコマンド

### SVGレンダリング (ドキュメント用)
```powershell
node scripts/render.mjs --input diagram.mmd --output diagram.svg --theme tokyo-night
```
- **推奨テーマ**: `tokyo-night` (ダークモード用), `github-light` (ライトモード用)

### ASCIIレンダリング (README・ターミナル表示用)
```powershell
node scripts/render.mjs --input diagram.mmd --format ascii --use-ascii
```

---

## 3. Iris特化型 Mermaid テンプレート

### A. 層アーキテクチャ図 (flowchart)
各層の境界と、EventBusを介した疎結合な関係性を示すための標準構成。

```mermaid
flowchart TB
    subgraph KernelLayer["kernel (脳幹)"]
        manager["KernelManager"]
        process["KernelProcess"]
        factory["DI Factory"]
    end
    subgraph IoLayer["io (視床)"]
        io_mgr["IOManager"]
        grpc["GrpcListener"]
    end
    subgraph EventLayer["event (神経路)"]
        bus["EventBus"]
    end
    subgraph HeartbeatLayer["heartbeat (TimerTick)"]
        hb_svc["HeartbeatService"]
    end
    subgraph MemoryLayer["memory (記憶系)"]
        mem_mgr["MemoryManager"]
        sensory["SensoryMemory"]
        stm["ShortTermMemory"]
        ltm["LongTermMemory"]
    end
    subgraph AgencyLayer["agency (高度認知)"]
        planning["PlanningManager"]
        execution["ExecutionOrchestrator"]
    end
    subgraph LlmLayer["llm (LLM基盤)"]
        bridge["LLMBridge"]
    end

    %% 依存関係（EventBus経由の疎結合）
    KernelLayer -.-> bus
    IoLayer -.-> bus
    HeartbeatLayer -.-> bus
    MemoryLayer -.-> bus
    AgencyLayer -.-> bus
```

### B. EventBus 連携シーケンス図 (sequenceDiagram)
イベント発行と各層の並列処理を示すための標準構成。

```mermaid
sequenceDiagram
    participant A as AgencyManager
    participant E as EventBus
    participant H as HeartbeatService
    participant M as MemoryManager

    A->>E: publish(AgentActionEvent)
    activate E
    E-->>H: notify(AgentActionEvent)
    E-->>M: notify(AgentActionEvent)
    deactivate E

    activate H
    H->>H: TimerTick処理
    H->>E: publish(TimerTick)
    deactivate H

    activate M
    M->>M: 記憶保存
    deactivate M
```

---

## 4. トラブルシューティング

- **Syntax Errorでビルド失敗**:
  - `A --> B` などの矢印の間にスペースがあるか確認。
  - クラス図の型指定で `<` や `>` などの特殊文字を使用する場合はエンコードするか、ダブルクォーテーションで囲む。
- **beautiful-mermaid モジュールエラー**:
  - `.agents/skills/iris-visualize/` ディレクトリ内で `npm install` を実行する。
