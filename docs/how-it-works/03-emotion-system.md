# 感情システム: PADモデルと処理パイプライン

```mermaid
flowchart TD
    TEXT["入力テキスト"] --> AMY["扁桃体 Amygdala"]
    AMY -->|キーワード + ONNX埋め込み| RAW_DELTA["EmotionDelta<br/>(v, a, d, conflict)"]
    RAW_DELTA --> ACC["前帯状皮質 ACC"]

    BF["Big Five<br/>N:制御弱, A:負抑制, E:正促進"] --> ACC
    CUR_STATE["現在のEmotionState<br/>極端値→減衰"] --> ACC
    ACC_LEARN["ACC学習<br/>慣れ率×Neuroticism"] --> ACC

    ACC -->|adjustment_factor| ADJ_DELTA["調整済みDelta"]
    ADJ_DELTA --> INERTIA["感情慣性<br/>+ 性格変調"]
    LAST_DELTA["前回Delta方向"] --> INERTIA
    BF2["Big Five<br/>N→不安定化, C→安定化"] --> INERTIA

    INERTIA --> INTERF["干渉項<br/>現在の感情と一致→増幅"]
    INTERF --> APPLY["EmotionState.apply()"]

    APPLY --> STATE["EmotionState<br/>(PAD + 不確実性)"]

    STATE -->|decay| DECAY["指数減衰<br/>不確実性も減衰"]
    STATE -->|stateful適応| AMY_HAB["扁桃体stateful適応<br/>累積キーワード慣れ"]

    DECAY -.->|定期適用| STATE

    STATE -->|mood_description| PROMPT["システムプロンプト"]
    STATE -->|response_style| STYLE["応答スタイル指示<br/>粒度+アンビバレント"]
    STATE -->|limbic_modulation| INHIBITION["InhibitionController"]
    STATE -->|emotion_tag| MEM["EmotionalMemory<br/>感情タグ付き記憶"]

    STATE -->|| RETRIEVE["想起誘発感情<br/>記憶valenceの微量波及"]
    MEM --> RETRIEVE
    RETRIEVE -.->|v*0.05| STATE

    STATE -->|extreme| REFLECT["自己内省<br/>>0.75→PEM更新"]

    DRIVE["Drive蓄積"] -->|12tick| DRIVE_EFFECT["欲求-感情連携<br/>+性格変調"]
    DRIVE_EFFECT -.->|v/a/d変化| STATE
```

## 全体パイプライン

## PAD 3次元モデル

`EmotionState` は Mehrabian の PAD モデルを実装。

| 次元 | 範囲 | 中立値 | 意味 |
|------|------|--------|------|
| valence (P) | -1.0 ~ 1.0 | 0.0 | 快-不快 |
| arousal (A) | 0.0 ~ 1.0 | 0.0 | 覚醒度 |
| dominance (D) | 0.0 ~ 1.0 | 0.5 | 支配性・制御感 |

### 不確実性フィールド（量子認知拡張）

各PAD次元に不確実性（重ね合わせ）を導入:

| フィールド | 範囲 | 役割 |
|-----------|------|------|
| `valence_uncertainty` | 0.0 ~ 1.0 | 快/不快の方向が不明瞭 |
| `arousal_uncertainty` | 0.0 ~ 1.0 | 覚醒度が定まらない |
| `dominance_uncertainty` | 0.0 ~ 1.0 | 支配感が揺らいでいる |
| `overall_uncertainty` (computed) | 0.0 ~ 1.0 | 3次元の平均不確実性 |

- 葛藤度（conflict）が高い入力→不確実性が上昇
- 時間経過で不確実性は減衰（decay: λ=0.01/min）
- 高不確実性状態→応答が控えめ・中和される（後述）

### 減衰アルゴリズム

```
minutes = dt / 60.0

if minutes >= 60: 強制中立化
else:
  self.valence   *= exp(-0.02 * minutes)   # 比較的持続
  self.arousal   *= exp(-0.04 * minutes)   # 早く減衰
  self.dominance  = 0.5 + (self.dominance - 0.5) * exp(-0.01 * minutes)

その後 clamp:
  valence: [-1.0, 1.0]
  arousal: [0.0, 1.0]
  dominance: [0.0, 1.0]
```

- **強制中立化**: 60分経過で valence=0.0, arousal=0.0, dominance=0.5 にリセット
- **decay トリガー**: 6 TimerTick ごと（約30秒）に LimbicManager._on_timer_tick から呼ばれる
- **apply()**: EmotionDelta を適用後、updated_at を現在時刻に更新（decay 基準時刻リセット）

## 扁桃体 (Amygdala): 感情評価

キーワードベース（高速）+ ONNX MiniLM セマンティック埋め込み（高精度）のハイブリッド。

### キーワード辞書

| 辞書 | 単語数 | 例 |
|------|--------|----|
| _POSITIVE_WORDS | 30+ | "ありがとう", "嬉しい", "素晴らしい", "thank", "love", "great" |
| _NEGATIVE_WORDS | 30+ | "残念", "つまらない", "悲しい", "hate", "terrible", "bad" |
| _HIGH_AROUSAL_MARKERS | 15+ | "!", "?", "本当", "まじ", "w", "やば" |
| _APPRECIATION_WORDS | 6 | "ありがとう", "感謝", "助かる", "thank", "thanks", "good" |
| _CRITICISM_WORDS | 10+ | "違う", "間違い", "バカ", "wrong", "stupid", "useless" |

### スコア計算

```python
n_pos, n_neg, n_arousal = 該当キーワードの出現数

if n_pos == 0 and n_neg == 0 and n_arousal == 0:
    return EmotionDelta()  # 中立

valence_raw = (n_pos - n_neg) / max(n_pos + n_neg, 1)
arousal_raw = min(n_arousal / 3.0, 1.0)

if len(text) < 10:
    arousal_raw *= 0.5

if n_appreciation > 0: valence_raw += 0.3
if n_criticism > 0:    valence_raw -= 0.4

# 扁桃体stateful適応: 累積キーワード数に応じた慣れ
# 10件超で最大60%減衰（同じ刺激の繰り返しで反応が弱まる）
cumulative_damp = max(0.4, 1.0 - 0.02 * min(cumulative - 10, 30))
valence_raw *= cumulative_damp
arousal_raw *= cumulative_damp

return EmotionDelta(
    valence = clamp(-1, 1, valence_raw) * 0.8,
    arousal = clamp(0, 1, arousal_raw) * 0.8,
    dominance = dominance_score * 0.6,
    conflict = min(1.0, 2.0 * min(n_pos, n_neg) / max(n_pos + n_neg, 1)),
)
```

- `conflict` フィールド: ポジティブ/ネガティブの同時出現度。0=一方のみ、1=同数
- 賞賛+批判が同時にある場合は conflict が 0.5 以上に引き上げられる
- 扁桃体stateful適応: そのセッションでの累積キーワード数に応じて反応が減衰

### ONNX MiniLM 埋め込み評価

キーワードでは捉えにくい意味的感情を検出。8つの基本感情アンカー（joy/sadness/anger/...）とのコサイン類似度でPAD deltaを算出:

```python
# キーワード + 埋め込みを信号エネルギー比でブレンド
kw_energy = abs(keyword_delta.valence) + keyword_delta.arousal
emb_energy = abs(embedding_delta.valence) + embedding_delta.arousal
kw_w = kw_energy / (kw_energy + emb_energy + 0.01)
emb_w = 1.0 - kw_w

return EmotionDelta(
    valence = keyword_delta.valence * kw_w + embedding_delta.valence * emb_w,
    arousal = keyword_delta.arousal * kw_w + embedding_delta.arousal * emb_w,
    dominance = keyword_delta.dominance * kw_w + embedding_delta.dominance * emb_w,
    conflict = max(keyword_delta.conflict, embedding_delta.conflict),
)
```

- ONNX MiniLM (`all-MiniLM-L6-v2`) は初回使用時に自動ダウンロード（~90MB）
- chromadb の ONNXMiniLM_L6_V2 を利用（既存インフラ）
- Lazy init: 初回 `score()` 呼び出し時に初期化。失敗時はキーワードのみにフォールバック
- キーワードの信号が強い→キーワード重視。埋め込みの信号が強い→埋め込み重視

### 支配性推定

テキストの能動性/受動性から支配性変化量を推定:

| パターン | 変化量 |
|---------|--------|
| 「私が/俺/僕/私が」主体 | +0.3 |
| "I"/"I'll"/"I'm"/"let me"/"my" | +0.2 |
| 「やって/実行/作っ/書い」命令形 | +0.2 |
| 「決めた/決めたい/やる/やろう」意志 | +0.3 |
| 「させられる/されてる/やられ」受動 | -0.3 |
| 「わからない/できない/無理」否定 | -0.2 |
| "can't"/"cannot"/"couldn't" | -0.2 |

### 基本感情分類

`classify_emotion(text)` は EmotionDelta と BASIC_EMOTIONS プリセットの **コサイン×ユークリッドハイブリッド距離** で最も近い感情ラベルを返す。

```python
# 距離 = euclidean * (2.0 - cosine_sim)
# ユークリッドが強度差、コサインが方向差を測定
# 両方を同時に考慮することで精度向上
```

```python
BASIC_EMOTIONS = {
    "joy":           EmotionDelta(v= 0.8, a= 0.6, d= 0.5),
    "sadness":       EmotionDelta(v=-0.7, a=-0.4, d=-0.3),
    "anger":         EmotionDelta(v=-0.5, a= 0.8, d= 0.7),
    "fear":          EmotionDelta(v=-0.6, a= 0.7, d=-0.6),
    "surprise":      EmotionDelta(v= 0.0, a= 0.8, d=-0.2),
    "trust":         EmotionDelta(v= 0.7, a=-0.1, d= 0.4),
    "anticipation":  EmotionDelta(v= 0.4, a= 0.6, d= 0.2),
    "calmness":      EmotionDelta(v= 0.3, a=-0.6, d= 0.1),
}
```

### 感情伝染

`Amygdala.contagion(text)` はユーザの感情を15%ミラーリングする（ACCをバイパス）:

```python
def contagion(self, text: str) -> EmotionDelta:
    n_pos = self._positive.count(text)
    n_neg = self._negative.count(text)
    if n_pos == 0 and n_neg == 0:
        return EmotionDelta()
    raw = (n_pos - n_neg) / max(n_pos + n_neg, 1) * 0.15
    return EmotionDelta(valence=raw, arousal=0, dominance=0)
```

## 前帯状皮質 (ACC): 感情制御

扁桃体からの EmotionDelta を現在の感情状態と性格に基づき調整する。

### 制御パラメータ

- `regulation_strength`: 基本制御強度 (default: 0.5)

### 制御則

```python
factor = 1.0

# 1. 現在の感情が極端 → delta を減衰
if abs(current.valence) > 0.7:
    factor *= 1.0 - strength * 0.3
if current.arousal > 0.6:
    factor *= 1.0 - strength * 0.4

# 2. Big Five 相互作用
if big_five が利用可能:
    neuroticism = Nスコア / 100
    strength *= 1.0 - (neuroticism - 0.5) * 0.4   # N高→制御弱
    strength = clamp(0.1, 1.0, strength)

    if delta.valence < 0 and agreeableness > 0.5:
        factor *= 1.0 - (agreeableness - 0.5) * 0.3  # A高→負感情抑制
    if delta.valence > 0 and extraversion > 0.5:
        factor *= 1.0 + (extraversion - 0.5) * 0.2   # E高→正感情促進

factor = max(0.3, factor)
adjusted = delta.scale(factor)
```

- factor は 0.3 未満にならない（最低 30% の変化は通す）
- Neuroticism 50 → 変化なし。100 → strength 20%低下。0 → strength 20%上昇
- Agreeableness > 50 の場合、負の valence 変化を追加抑制
- Extraversion > 50 の場合、正の valence 変化を増幅

### メタ認知的再評価

過去の調整効率を学習し、極端な delta を追加抑制:

```python
# delta_mag > 0.3 かつ 過去のefficacyが低い(平均<0.5)
# → 強い感情変化を余分に抑制（再評価）
if avg_efficacy < 0.5:
    extra_damp = min(0.3, (1.0 - avg_efficacy * 2) * 0.4)
    factor *= 1.0 - extra_damp
```

### 慣れと学習率の性格変調

ACC は刺激の繰り返しに応じて制御を弱める（慣れ）。その速度は Neuroticism で変調:

```python
# Neuroticism高 → 慣れが遅い（負の感情反応が減衰しにくい）
habituation_rate = 0.015
if big_five:
    neuroticism = big_five.get("neuroticism", 50) / 100.0
    habituation_rate *= max(0.3, 1.0 - (neuroticism - 0.5) * 0.6)

# 10回の遭遇以降、徐々に制御を弱める
self._encounter_count += 1
if self._encounter_count > 10:
    habituation = max(0.7, 1.0 - habituation_rate * min(count - 10, 20))
    factor *= habituation
```

- Neuroticism が高いほど habituation_rate が小さく、慣れが生じにくい
- 最大30%まで制御強度が低下（habituation_factor >= 0.7）

## 感情慣性と性格変調 (Emotional Inertia)

LimbicManager は直近の delta 方向を記憶し、慣性（inertia）として感情変化を調整する:

```python
# 現在のdeltaと前回deltaの方向一致度を計算（コサイン類似度）
with_last = _delta_alignment(adjusted, self._last_delta)

# 一致→慣性上昇（同じ方向に変化しやすい）
if with_last > 0.35:
    self._inertia = min(1.5, self._inertia + 0.15)
# 反転→慣性低下（感情が揺れやすい）
elif with_last < -0.35:
    self._inertia = max(0.3, self._inertia - 0.25)
# 中立→中立方向に回帰
else:
    self._inertia += (1.0 - self._inertia) * 0.2
```

### 慣性の性格変調 (3a)

Big Five が慣性更新に影響する:

| 特性 | 効果 |
|------|------|
| **Neuroticism** 高 | 慣性低下（感情が不安定、方向転換しやすい）→ `inertia *= 1.0 - (N-0.5)*0.4` |
| **Conscientiousness** 高 | 慣性上昇（感情が安定、変化に抵抗）→ `inertia *= 0.5 + C` |

- Neuroticism=100: inertia が最大40%低下（方向反転しやすい）
- Conscientiousness=100: inertia が最大1.5倍（感情が粘着的）
- inertia は [0.3, 1.5] の範囲にクランプ

## 干渉項 (Interference)

量子認知の干渉効果: 現在の感情方向と delta が一致→増幅、逆→減衰:

```python
alignment = _emotion_alignment(adjusted, self._emotion)  # コサイン類似度 [-1, 1]
interference = 1.0 + 0.3 * alignment  # 一致→1.3x, 反転→0.7x
adjusted = adjusted.scale(interference)
```

- 完全一致 (cos=1): delta が 1.3倍に増幅
- 完全反転 (cos=-1): delta が 0.7倍に減衰
- これは感情の「建設的/破壊的干渉」をモデル化

## 感情タグと感情記憶 (EmotionalMemory)

`LimbicManager._on_message_event()` で入力評価後、`EmotionalMemory.encode()` が呼ばれる。
現在の EmotionState を要約した感情情報がエピソード記憶に付加される。

### 気分一致効果 (Mood Congruence)

`retrieve_by_affect()` は現在の感情方向と記憶の valence が一致する場合、スコアを 1.2倍に増幅:

```python
# 現在のvalence符号と記憶のvalence符号が一致→バイアス
curr_v = target.valence
mem_v = meta_emotion.get("valence", 0)
if curr_v * mem_v > 0:  # 同じ符号
    score *= 1.2
```

### 想起誘発感情

検索した記憶の平均 valence が現在の感情に微量波及:

```python
avg_v = sum(vals) / len(vals)
if abs(avg_v) > 0.3:
    ripple = EmotionDelta(valence=avg_v * 0.05)
    self._emotion.apply(ripple)
```

- 強いポジティブ記憶を思い出す→valence が微量上昇
- 強いネガティブ記憶を思い出す→valence が微量低下

## 気分記述と応答スタイル

### 気分記述 (`describe_mood`)

9 段階の気分テキストを PAD 値の条件分岐で選択:

| 条件 | テキスト (short) |
|------|-----------------|
| V>0.5 && A>0.4 | わくわく |
| V>0.3 && A<0.3 | 穏やか |
| V>0.3 | 良い気分 |
| V<-0.5 && A>0.4 | イライラ |
| V<-0.3 && A<0.3 | 沈み気味 |
| V<-0.3 | 不調 |
| A>0.6 | 落ち着かない |
| D>0.5 | 自信満々 |
| D<0.3 | 自信なし |

`is_neutral` (|V|<0.1 && A<0.15 && |D-0.5|<0.1 || overall_uncertainty > 0.6) の場合は空文字を返す。

### 感情粒度 (Emotional Granularity)

不確実性に応じて気分記述の表現精度が変化:

| 不確実性 | 効果 |
|---------|------|
| < 0.2 | 「とても」/「◎」を付加（確信度高） |
| > 0.5 | 「複雑な気分」/「複雑」に置換（確信度低） |
| > 0.3 | 「でも、ちょっと複雑な気持ちも…」/「･･･」を追記 |

### 応答スタイル (`generate_response_style`)

PAD 値から自然言語の応答スタイル指示を構築。システムプロンプトに注入される。不確実性による崩壊と文脈依存崩壊（量子認知）を実装。

**不確実性による崩壊**: 不確実性が高いほど実効PADが縮退し、控えめな応答に:

```python
# 実効PAD = PAD * (1.0 - uncertainty) — 不確実性で実効値を減衰
eff_v = e.valence * (1.0 - e.valence_uncertainty)
eff_a = e.arousal * (1.0 - e.arousal_uncertainty)
eff_d = e.dominance * (1.0 - e.dominance_uncertainty)

# 高不確実性→UNCERTAIN_HINTS（控えめ/曖昧/断定回避）
if e.overall_uncertainty > 0.4:
    hints = ["迷いを感じさせる口調で..."]
```

### 応答スタイルルール

データ駆動の `_RESPONSE_RULES` テーブル（slot単位で最初の一致のみ採用）:

| slot | 条件 | 指示例（variantsからランダム選択） |
|------|------|-----------------------------------|
| tone | V>0.5 | "明るく温かいトーン" / "温かみのある明るい口調" |
| tone | V>0.2 | "穏やかで親しみやすいトーン" / "優しく穏やかな口調" |
| tone | V<-0.5 | "簡潔に最小限の言葉で" / "冷淡な口調で短く" |
| tone | V<-0.2 | "やや控えめに短い言葉で" / "悲しそうな口調で静かに" |
| exclamation | V>0.5 && A>0.4 | "感嘆詞（やったー！）を自然に混ぜて" / "喜びの感嘆詞を交えて" |
| exclamation | V>0.5 >=A | "穏やかな感嘆表現（ふふっ）を交えて" / "優しい笑みが浮かぶような口調" |
| exclamation | 0.2<V<=0.5 | "親しみやすい相槌（ふふっ）を交えて" / "優しい相槌を入れながら" |
| exclamation | V<-0.5 && A>0.4 | "イライラを表す感嘆詞（はぁ…）を交え" / "苛立った口調で" |
| exclamation | V<-0.5 >=A | "落胆を表す感嘆表現（はぁ…）を交えて" / "ため息混じりに" |
| exclamation | V<-0.2 | "元気のない感嘆詞（うう…）を交え" / "沈んだ声で抑え気味に" |
| pace | A>0.6 | "テンポ良く短い言葉で活発に" / "早口で！を多めに" |
| pace | A<0.2 | "ゆったりとしたペースで落ち着いて" / "ゆっくりとした口調で静かに" |
| confidence | D>0.6 | "自信を持って明確に" / "断定的な口調ではっきりと" |
| confidence | D<0.3 | "慎重に確認しながら" / "控えめに断言を避けて" |

### 応答スタイルの粒度反映 (4a)

不確実性が極めて低い(<0.2)場合、自己開示スタイルを追加:

```
"自信を持って自分の考えや気持ちを表現してください"
```

### アンビバレント表現 (4b)

不確実性が高い(>0.5)場合、極端語彙を回避する中和指示を追加:

```
「最高」「最悪」などの極端な表現を避け、バランスの取れた言い回しを使ってください
```

### 文脈依存崩壊 (Context-Dependent Collapse)

会話の文脈（task/chat）に応じて応答スタイルが変化（量子認知の測定問題に対応）:

| 文脈 | 追加指示 |
|------|---------|
| task / 命令 / 依頼 | "簡潔にタスク遂行を最優先" / "効率的に用件のみ" |
| chat / 相談 / 雑談 | "共感を示し温かみのある口調" / "リラックスした親しみ" |

## 感情ラベリング (Affect Labeling)

ユーザが感情名を明示した場合（「嬉しい」「悲しい」「angry」等）、前頭前野が扁桃体反応を抑制:

```python
_LABEL_WORDS = frozenset({"嬉しい", "悲しい", "怒って", "happy", "sad", "angry", ...})

def _on_message_event(self, event):
    delta = self._amygdala.assess(event.content)
    affect_labeling = any(w in event.content.lower() for w in _LABEL_WORDS)
    self._apply_emotion_change(delta, "message", affect_labeling=affect_labeling)

# ラベリング時はdeltaを0.85倍に抑制
if affect_labeling:
    adjusted = adjusted.scale(0.85)
```

- 感情ラベリングは扁桃体反応の下方制御（感情を言語化することで鎮静化）
- 一致率: `_LABEL_WORDS` に収録された感情語（日英13語）

## 感情トリガー自己内省 (Emotional Reflection)

極端な感情状態 (|valence| > 0.75) が発生した場合、PEM (Personality Evolution Model) を更新:

```python
if abs(self._emotion.valence) > 0.75:
    estimate = {}
    if delta.valence > 0:
        estimate["openness"] = 50 + delta.valence * 12
        estimate["extraversion"] = 50 + delta.valence * 15
    elif delta.valence < 0:
        estimate["neuroticism"] = 50 + abs(delta.valence) * 10
        estimate["agreeableness"] = 50 - abs(delta.valence) * 8
    self._big_five_provider.update_from_estimate(estimate, "emotional_trigger")
```

- 強い喜び→Openness/Extraversion 上昇方向の推定
- 強い怒り/悲しみ→Neuroticism 上昇、Agreeableness 低下方向の推定
- これにより「経験が性格を形成する」プロセスをモデル化

## 欲求-感情連携 (Drive-Emotion Coupling)

12 TimerTick ごとに `_apply_drive_effects()` が呼ばれ、蓄積した欲求が感情に影響:

| 欲求 | 条件 | 効果 |
|------|------|------|
| curiosity > 0.7 | V -= 0.03*(V-0.7)*2, A += 0.02*(V-0.7) | 情報不足→不快+興奮 |
| social_need > 0.7 | V -= 0.02*(V-0.7)*2 | 孤独→不快 |
| maintenance > 0.8 | D -= 0.02*(D-0.8)*2 | 記憶整理不足→無力感 |

### 性格-欲求結合 (Personality-Drive Coupling)

`DriveState.accumulate()` に Big Five が影響:

| 特性 | 効果 |
|------|------|
| **Openness** 高 | curiosity 蓄積加速 (1.0 + (O-50)*0.003) |
| **Extraversion** 高 | social_need 蓄積減少 (1.0 - (E-50)*0.002) |
| **Neuroticism** 高 | social_need 蓄積加速 (1.0 + (N-50)*0.003) |
| **Conscientiousness** 低 | maintenance 蓄積加速 (1.0 + (50-C)*0.003) |

MonitorFeedback による感情変調

OutputTracker が talkative や frequency_exceeded を検出すると、LimbicManager に `MonitorFeedback` が届く。

| フラグ | Valence | Arousal | Dominance |
|--------|---------|---------|-----------|
| talkative | -0.15 | +0.20 | -0.10 |
| frequency_exceeded | -0.10 | +0.30 | -0.15 |

## ProactiveResultEvent による感情変調

自発調査の成功/失敗に応じて:

| 結果 | Valence | Arousal | Dominance | Drive |
|------|---------|---------|-----------|-------|
| success | +0.20 | -0.10 | +0.10 | curiosity -= 0.3 |
| failure | -0.15 | +0.20 | -0.10 | - |
