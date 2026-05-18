# ADR-001: 大脳辺縁系（Limbic System）層の追加

## ステータス

提案中

## コンテキスト

Iris は脳科学・神経科学に基づく層分割アーキテクチャを採用している。

| 現行層 | 脳部位 | 責務 |
|--------|--------|------|
| `kernel/` | 脳幹+視床下部 | プロセス管理・駆動 |
| `io/` | 視床 | 入出力中継 |
| `memory/` | 感覚野+海馬+皮質 | 記憶・学習 |
| `agency/` | PFC+基底核+運動野 | 意思決定・行動実行 |
| `event/` | 神経路 | 全層間通信 |

しかし、**感情処理**を司る**大脳辺縁系（Limbic System）** に対応する層が存在しない。
Neuro-sama のような人間的な振る舞いには、以下の機能が必要:

- 入力に対する感情評価（これは嬉しい？悲しい？）
- 感情状態の動的変化と自然減衰
- 感情に基づく応答スタイルの変化
- 記憶への感情タグ付け（感情的な記憶ほど強く残る）
- 感情と性格特性（Big Five）の相互作用

これらの責務を既存層に押し込むと、単一責任の原則に反する。

## 決定

**`iris/limbic/` 層を新設する。**

大脳辺縁系を構成する以下の脳部位をコード構造にマッピングする:

| ファイル | 脳部位 | 責務 |
|----------|--------|------|
| `manager.py` | 辺縁系全体の統括 | 感情状態管理、EventBus連携、他層との統合 |
| `models.py` | — | 感情状態データモデル（PAD次元） |
| `amygdala.py` | 扁桃体 | 入力の感情評価、価値判断、感情反応トリガー |
| `acc.py` | 前帯状皮質 | 感情制御・葛藤調整、InhibitionControllerへの感情シグナル供給 |
| `emotional_memory.py` | 扁桃体-海馬相互作用 | 記憶への感情タグ付け、感情ベースの記憶検索 |

## 根拠

1. **脳科学との一貫性**: 大脳辺縁系は解剖学的に脳幹と大脳皮質の間に位置する独立したシステム。既存の層構成パターンに自然に適合する。
2. **単一責任**: 感情処理は記憶（memory/）や意思決定（agency/）とは異なる責務。分離により各層の凝集度が高まる。
3. **拡張性**: 独立した層とすることで、将来のTTS感情表現やLive2D表情制御への拡張が容易。
4. **既存パターンの踏襲**: EventBus購読/公開による他層との疎結合、FactoryによるDI注入など、既存アーキテクチャパターンをそのまま適用できる。

## 影響

### 追加されるコンポーネント

- `iris/limbic/manager.py` — `LimbicManager`
- `iris/limbic/models.py` — `EmotionState` dataclass
- `iris/limbic/amygdala.py` — `Amygdala`
- `iris/limbic/acc.py` — `AnteriorCingulateCortex`
- `iris/limbic/emotional_memory.py` — `EmotionalMemory`

### 変更が必要な既存コンポーネント

- `iris/kernel/factory.py` — `LimbicManager` のインスタンス生成・依存注入
- `iris/llm/`（LLMPipeline / context_window） — システムプロンプトへの感情状態注入
- `iris/agency/planning/scoring.py` — 感情因子の ProactiveScoring への統合
- `iris/agency/execution/inhibition.py` — 感情による抑制制御の変調
- `iris/memory/personality/` — Big Five 性格特性モデルとの相互作用
- `iris/memory/hippocampal/reflexion.py` — Reflexion への感情タグ参照

### 新規 EventBus イベント（必要に応じて追加）

- `EmotionUpdate` — 感情状態変化の通知

### 新規データファイル

- `.iris/data/big_five.json` — Big Five スコアの永続化
- `.iris/data/emotion_state.json` — 感情状態のスナップショット（永続化任意）

## 代替案

### A. 感情処理を `agency/` に統合

PFC/基底核と同階層に感情モジュールを配置する案。
却下理由: 感情は行動だけでなく記憶や知覚にも影響するため、agencyの責務範囲を超える。

### B. 感情処理を `memory/` に統合

emotional_memory は memory/ に適合するが、感情評価（扁桃体）や感情制御（ACC）は別責務。
却下理由: 単一責任の原則に反する。

### C. 感情処理を既存層に横断的に分散

各層に小さな感情モジュールを配置する案。
却下理由: 層間の暗黙的依存が増加し、アーキテクチャの明確さが損なわれる。
