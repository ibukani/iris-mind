# 自発発話スコアリング: ProactiveScoring

前頭前野 (PFC) が自発行動の価値を評価するスコアリング。
`PlanningManager._handle_proactive_event()` でタイマー起動時に呼ばれる。

```mermaid
flowchart LR
    subgraph Factors["8 因子"]
        T["time<br/>経過時間"]
        M1["memory<br/>長期記憶類似度"]
        CTX["context<br/>Bigram Jaccard"]
        MD["mood<br/>PAD加重"]
        D["drive<br/>max(3欲求)"]
        SN["sensory<br/>未処理入力有無"]
        STM["short_term<br/>ターン数"]
        URG["urgency<br/>緊急キーワード"]
    end

    subgraph Weights["重み付け"]
        WT["w×time 0.25"]
        WM["w×memory 0.45"]
        WC["w×context 0.15"]
        WMO["mood_weight 動的"]
        WD["w×drive 0.20"]
    end

    subgraph Adjust["最終調整"]
        SN -->|>0 → max ≥ 0.18| TOTAL
        URG -->|>0 → max ≥ 0.015| TOTAL
        IG["ignore_penalty"] -->|×max(0.2, 1-0.25×n)| TOTAL
        SYS_EVT["system_event"] -->|強制通過| TOTAL
    end

    T --> WT
    M1 --> WM
    CTX --> WC
    MD --> WMO
    D --> WD

    WT --> SUM["Σ"]
    WM --> SUM
    WC --> SUM
    WMO --> SUM
    WD --> SUM

    SUM --> TOTAL["total score"]
    TOTAL --> TH{"threshold?"}
    TH -->|"≥ speak_threshold"| PASS["通過 → 発話"]
    TH -->|"< speak_threshold"| ABORT["abort → 何もしない"]
```

## スコア統合

```python
total = (
    w_time    * time_score
    + w_memory * memory_score
    + w_context * context_score
    + mood_weight * mood_score
    + w_drive  * drive_score
)
```

### デフォルト重み

| 重み | デフォルト値 | config キー |
|------|-------------|-------------|
| w_time | 0.40 | trigger_weights.time |
| w_memory | 0.35 | trigger_weights.memory |
| w_context | 0.15 | trigger_weights.context |
| w_mood | 0.10 | trigger_weights.mood |

## 各因子の計算式

### 1. time_score

前回行動（proactive or user）からの経過時間に基づくスコア。

```python
last_time = max(last_proactive_time, last_user_activity)
if last_time == 0: return 0.0

elapsed = now - last_time
if elapsed < config.min_interval_sec: return 0.0  # 最小間隔未満は0

ratio = (elapsed - min_interval) / (max_interval - min_interval)
return min(ratio, 1.0)
```

config 値:
- `min_interval_sec`: 最小間隔（デフォルト 30秒）
- `max_interval_sec`: 最大間隔（デフォルト 300秒）

### 2. memory_score

長期記憶との関連性。現在の話題と意味記憶の類似度。

```python
recent = memory.get_recent(3)        # 直近3件の短期話題
topic = " ".join(summary)            # 話題連結
results = memory.search_semantic(topic)  # ChromaDB+BM25検索
return max(results.scores)           # 最高類似度
```

- 話題がない場合: 0.0
- 検索失敗: 0.0
- 意味記憶との接続が多いほど高スコア

### 3. context_score

直近会話の文脈的一貫性。文字bigram Jaccard類似度。

```python
recent = memory.get_recent(2)        # 直近2件
if len(recent) < 2: return 0.3       # データ不足→中程度

summaries = [item.summary for item in recent]
if all(len(s) < 10): return 0.7      # 短い話題→高いスコア

bigram_a = char_bigram_set(summaries[0])
bigram_b = char_bigram_set(summaries[1])
jaccard = len(intersection) / len(union)
return min(jaccard + 0.2, 1.0)       # +0.2 バイアス
```

- 短期記憶のターン数に基づく stm_score が context_score より高い場合はそちらを採用

### 4. stm_score (短期記憶追加因子)

```python
turns = memory.short_term.get_recent_turns(2)
if len(turns) >= 2: return 0.5
if len(turns) == 1: return 0.3
return 0.0
```

### 5. sensory_score (感覚記憶追加因子)

```python
sensory = memory.sensory.retrieve()
if "raw" in sensory: return 0.6  # 未処理の生入力あり
return 0.0
```

sensory_score > 0 の場合、`total = max(total, sensory_score * 0.3)` で最低保証。

### 6. urgency_score (緊急性因子)

```python
score = 0.0
if "?"/"？"/"教えて"/"what"/"how"/"why": score += 0.3
if "urgent"/"important"/"急"/"至急"/"help"/"問題": score += 0.3
if len(content) > 100: score += 0.2
if content.count("!") >= 2: score += 0.1
return min(score, 0.8)
```

### 7. drive_score

```python
max(curiosity, social_need, maintenance)
```

3欲求の最大値。0.0 ~ 1.0。

## 最終調整

```python
# sensory 最低保証
if sensory_score > 0:
    total = max(total, sensory_score * 0.3)

# urgency 最低保証
total = max(total, urgency_score * 0.15)

# ignore ペナルティ
if ignore_count > 0:
    ignore_penalty = max(0.2, 1.0 - ignore_count * 0.25)
    total *= ignore_penalty

# システムイベントは強制通過
if system_event == "connected":
    total = max(total, speak_threshold + 0.1)
```

### ignore ペナルティの減衰

| consecutive_ignores | penalty |
|--------------------|---------|
| 0 | 1.0 (影響なし) |
| 1 | 0.75 |
| 2 | 0.50 |
| 3 | 0.25 |
| 4+ | 0.20 (下限) |

### 閾値

- `speak_threshold`: 発話閾値（発話するために超えるべきスコア、設定値）
- 超えなければ `abort` → その TimerTick では何もしない
