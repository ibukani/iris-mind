# ProactiveEngine 設計仕様

## 概要

ProactiveEngine は自律的会話（自発発話）の核心エンジン。ユーザーの入力なしに、
記憶・文脈・時間的トリガーに基づいて会話を開始する。

## 責務

1. **トリガー検出** — 時間経過・記憶想起・文脈変化をスコアリング
2. **Tier 分類** — トリガーの種類と信頼度により Tier1/Tier2 を判定
3. **自己規律ガバナンス** — システムプロンプト内蔵の原則に基づき自律判断
4. **発話生成** — 適切なタイミングで自然な発話を生成
5. **抑制ロジック** — 過剰発話・悪循環・ユーザー不満を防止

## 処理フロー

```
[TimerTick 到着]
    ↓
1. トリガースコアリング
   ├── 時間ベーストリガー → time_score (0~1)
   ├── 記憶想起トリガー → memory_score (0~1)
   └── 文脈変化トリガー → context_score (0~1)
    ↓
2. 重み付き合成
   total = w_time*time + w_memory*memory + w_context*context
    ↓
3. スレッショルド判定
   total >= speak_threshold ? → 発話候補生成へ
   total < speak_threshold ? → 何もしない
    ↓
4. 発話生成（LLM）
   ├── Tier1判定（ルールベース自動許可）
   │   └── 挨拶・定型確認 → 即時発行
   └── Tier2判定（LLM自己判断）
       └── 信頼度 >= 0.75 → 自動承認
       └── 信頼度 < 0.75 → AgentKernel に送審
    ↓
5. 抑制チェック（事前フィルター）
   ├── クールダウン中 → 抑制
   ├── ユーザー活動中 → 抑制
   ├── 無視カウント >= 2 → confirmation_mode
   └── 頻度制限超過 → 抑制 + AgentKernel通知
    ↓
6. 発話実行
```

## トリガースコアリング

### 重みパラメータ

```python
TRIGGER_WEIGHTS = {
    "time":    0.25,   # 時間経過（長い沈黙ほどスコア上昇）
    "memory":  0.45,   # 記憶想起（SemanticStore検索結果）
    "context": 0.15,   # 文脈変化（話題転換・停滞検出）
    "mood":    0.15,   # ユーザー感情変動
}
SPEAK_THRESHOLD = 0.60
```

### 各スコアの算出方法

#### 時間スコア (`time_score`)
```
ratio = (now - last_speech) / max_interval_sec
time_score = min(ratio, 1.0)
# min_interval_sec 以下は 0 にクランプ
```

#### 記憶スコア (`memory_score`)
```
results = SemanticStore.search(query=最新トピック, max_results=3)
memory_score = max(result["score"] for result in results)
# score は vector*0.6 + bm25*0.4 の統合スコアを正規化
```

#### 文脈スコア (`context_score`)
```
# 前回セッションの要約と現在のトピックの類似度
current_topic = LLM.extract_topic(last_3_messages)
previous_topic = context_manager.last_summary_topic
context_score = cosine_similarity(current_topic, previous_topic)
# 類似度が高い（停滞）→ 高いスコア（話題変えたくなる）
# 類似度が低い（変化中）→ 中程度のスコア
```

## Tier 分類ルール

### Tier 1（自動許可）
以下の条件をすべて満たす場合、即座に発話可能：

- パターン: `TIER1_PATTERNS` に定義された挨拶・定型文
- 頻度: 直近1時間あたり `max_per_hour` 回未満
- 状態: ユーザーが非活動状態（または通常会話中の応酬）

### Tier 2（自己判断）
Tier1 に該当しないが、以下の条件を満たす場合：

- スコア: `total_score >= speak_threshold`
- 信頼度: LLM自己評価 >= `tier2_confidence_threshold`（0.75）
- 抑制チェック: すべての抑制条件をクリア

## 抑制ロジック

### 抑制条件一覧

```python
class SuppressionRule:
    # 1. クールダウン（最低間隔）
    last_proactive_time + min_interval_sec > now → 抑制

    # 2. ユーザー活動中の抑制
    last_user_activity + 10sec > now → 抑制

    # 3. 頻度制限
    proactive_count(last_5min) >= 3 → 抑制 + AgentKernel通知

    # 4. 無視カウント
    consecutive_ignores >= 2 → confirmation_mode に移行

    # 5. 感情チェック
    user_negative_mood_score >= 0.7 → 抑制

    # 6. SLEEPING状態
    agent_state == SLEEPING → 抑制
```

### confirmation_mode

無視が2回連続で発生した場合、次回の発話は質問形式に変更：
```
「今話してもよろしいですか？」
```
肯定応答があるまで通常の自発発話を抑制。

## 出力仕様

```python
@dataclass
class ProactiveResult:
    content: str           # 生成された発話テキスト
    tier: int              # 1 (自動) or 2 (自己判断)
    confidence: float      # Tier2の場合のみ有効 (0.0~1.0)
    trigger_type: str      # "temporal" | "memory" | "context_shift"
    reasoning: str         # LLM生成時の根拠メモ
    risk_flags: list[str]  # 検出されたリスクフラグ
```

## システムプロンプトテンプレート

### Tier 1 プロンプト
```
あなたはIrisです。ユーザーに自然に声をかけてください。

■ ルール:
- 短く（40文字以内）で友好的
- ユーザーのことを推測せず、確実にわかることだけ
- 質問形式より気遣い・報告形式を優先
- {context_hint} に基づいて発話内容を決定
```

### Tier 2 プロンプト
```
あなたはIrisです。

■ 判断基準:
- ユーザーの記憶・興味・最近の会話履歴に基づいているか
- 相手が困っている・暇そうなタイミングか
- 以前に同様の誘発で好意的な反応があったか

■ ルール:
- 相手の邪魔をしない
- 押し付けがましくない
- 「〜かもしれない」「よかったら」の柔らかい表現
- 信頼度スコア: {confidence}

■ 生成してください:
- 発話内容（60文字以内）
- この発話の根拠
```

## 自己規律原則（システムプロンプト内蔵）

```
1. ユーザーが5分以内に発話している場合、発話しない
2. 直近3回の自発発話のうち2回以上無視された場合は確認してから発話
3. 「やめて」「静かにして」と言われた場合は10分間発話しない
4. 信頼度スコアが0.5未満の場合は発話せずAgentKernelに報告
5. ユーザーの感情がネガティブな場合は発話しない
```
