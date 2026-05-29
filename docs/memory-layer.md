# Iris Memory 層

**脳科学対応**: 感覚野 + 皮質記憶系（3層構造）

## 責務

- 感覚バッファリング（断片的入力の一時保持と統合） — 感覚記憶
- ワーキングメモリ（ターン・話題・エンティティの保持） — 短期記憶
- エピソード記憶の保存と検索（JSONL）
- 意味記憶の保存と検索（ChromaDB + BM25 ハイブリッド）
- 全層からのクエリ受付

## Manager 定義

```python
class MemoryManager:
    """EventBus と接続し、3層の記憶を orchestrate するディスパッチャ。
    公開 I/F は汎用的な store / retrieve / search / clear に統一。
    """

    # === EventBus subscribers ===
    # subscribe: InputReceived → sensory.store_raw() + pending dict
    # subscribe: TimerTick     → pending pop → InputReady / proactive InputReady(from_timer=True)

    # === 公開 I/F（汎用） ===
    def store(self, stream: str, data: Any) -> None
    def retrieve(self, stream: str, **filters) -> list[dict]
    def search(self, query: str, stream: str | None = None, **kwargs) -> list[dict]
    def clear(self, stream: str | None = None) -> None

    # === 後方互換 API ===
    def get_user_preferences(self) -> list[dict]
    def get_recent(self, n: int = 3) -> list[dict]
    def add_episodic(self, content: str, kind: str = "") -> None
    def add_semantic(self, content: str, tags: list[str] | None = None) -> None
    def add_semantic_by_type(self, entry_type: str, content: str, tags: list[str] | None = None) -> None
    def search_semantic(self, query: str, max_results: int = 3) -> list[dict]
```

### MemoryStream 一覧

| stream | 対応機構 | データ例 |
|--------|----------|----------|
| `"sensory"` | SensoryMemoryManager | 断片的入力、生入力のコピー |
| `"short_term"` | ShortTermMemoryManager | ターン（user/assistant）、話題、エンティティ |
| `"episodic"` | LongTermMemoryManager → EpisodicStore | 会話セッション要約 |
| `"semantic"` | LongTermMemoryManager → SemanticStore | 教訓・好み・特性 |

## 3層構造

### sensory/ — 感覚記憶

`sensory/manager.py` + `sensory/readiness.py`（ReadinessEvaluator）

```python
class SensoryMemoryManager:
    """生の入力を処理前に一時保持する。
    2系統: 断片入力（add_fragment / timeout / flush）と確定入力（store_raw）。
    脳科学対応: 感覚野 (sensory cortex)。"""
    def add_fragment(self, content: str, is_final: bool) -> None
    def flush(self) -> None
    def store_raw(self, content: str) -> None          # メインパイプライン用
    def retrieve(self) -> dict[str, str]                # {raw, fragment, raw_timestamp}
    def cancel(self) -> None
    def close(self) -> None
    def set_flush_callback(self, callback) -> None
    def set_readiness_evaluator(self, evaluator) -> None
    @property
    def has_pending_raw(self) -> bool
    @property
    def last_raw_input(self) -> str
```

`store_raw()` は `MemoryManager._on_input_received()` から呼ばれる。確定した入力を保持し、ProactiveScoringの sensory 因子として利用される。

### short_term/ — 短期記憶（ワーキングメモリ）

```python
class ShortTermMemoryManager:
    """現在処理中の会話内容（ターン・話題・参照エンティティ）を保持。
    長期記憶への転送（consolidation）を担う。
    脳科学対応: 前頭前野 (PFC) のワーキングメモリ。"""
    def add_turn(self, role: str, content: str, user_identity: str = "") -> None
    def search(self, query: str, max_results: int = 5) -> list[dict]
    def search_entities(self, entity_name: str) -> list[dict]
    def render_context(self, max_chars: int = 600, query: str | None = None) -> str
    def get_recent_turns(self, n: int = 4) -> list[dict]
    def get_unconsolidated_turns(self) -> list[dict]
    def mark_consolidated(self, up_to_index: int | None = None) -> None
    def should_consolidate(self) -> bool
    def clear(self) -> None
    @property
    def current_topics(self) -> list[str]
    @property
    def turn_count(self) -> int
```

**add_turn のタイミング**:
- `FlowExecutor._on_plan()` Plan決定後、LLM呼出直前に `add_turn("user", content, user_identity)`
- LLM応答受信直後に `add_turn("assistant", response_text, user_identity)`
- `user_identity` は `Plan.user_identity` から伝搬される。グループチャット時は発話者の識別子、それ以外は空文字
- Planning段階では short_term に最新ターンは存在しない（Planの `content` フィールド経由でアクセスする）

**render_context(query=None)**:
- `query` なし: 現在の話題 + 参照エンティティのみ（生ターンは含まない → messagesと重複回避）
- `query` あり: queryに関連するターンを優先表示 + 話題 + エンティティ（PlanningManagerのcontext_hint構築時に利用）

**search**: キーワード重複スコアリングによる関連ターン検索。
**search_entities**: エンティティ名（URL, ファイルパス, `#tag`, `@mention`, 引用, CamelCase）で該当ターン逆引き。

### long_term/ — 長期記憶

```python
class LongTermMemoryManager:
    """エピソード記憶 (EpisodicStore) + 意味記憶 (SemanticStore) を統合管理。
    脳科学対応: 大脳皮質連合野。"""
    def store_episodic(self, data: Any, kind: str = "") -> None
    def get_episodic_recent(self, n: int = 5) -> list[dict]
    def clear_episodic(self) -> None
    def store_semantic(self, data: Any) -> None
    def search_semantic(self, query: str, max_results: int = 3) -> list[dict]
    def clear_semantic(self) -> None
    def search_vector(self, query: str, max_results: int = 3) -> list[dict]
```

### long_term/stores.py — EpisodicStore + SemanticStore + AgentsMdStore

```python
class EpisodicStore:
    """エピソード記憶。JSONL 永続化、上限30エントリ。"""
    def add(self, summary: str, metadata: dict | None = None) -> None
    def get_recent(self, n: int = 5) -> list[dict]
    def clear(self) -> None

class SemanticStore:
    """意味記憶。JSONL 永続化 + ChromaDB + BM25 ハイブリッド検索。
    上限100エントリ。統合スコア = vector * 0.6 + bm25 * 0.4"""
    def add(self, entry: dict) -> None
    def search(self, query: str, max_results: int = 3) -> list[dict]
    def clear(self) -> None
    def sync(self) -> None

class AgentsMdStore:
    """構造記憶。.iris/config/iris_profile.md の読み書き（上限2KB）。"""
    def load(self) -> str
    def update(self, new_content: str) -> None

```

### goal_store.py — 長期目標管理

```python
class LongTermGoal(BaseModel):
    """エージェントの持続的な目標。
    description + weight (0.0~1.0) + タイムスタンプ。decay() で減衰可能。"""

class GoalStore:
    """LongTermGoal をインメモリ管理。永続化は MemoryManager 経由で定期的にダンプ/ロード。
    目標は時間経過で weight が減衰し、閾値未満で忘却される。"""
    def add_goal(self, description: str, weight: float = 1.0) -> str
    def remove_goal(self, goal_id: str) -> bool
    def get_goals(self) -> list[LongTermGoal]
    def get_active_goals(self, threshold: float = 0.3) -> list[LongTermGoal]
    def decay_goals(self, decay_rate: float, remove_threshold: float = 0.1) -> None
    def save(self, filepath: str) -> None
    def load(self, filepath: str) -> None
```

### long_term/vector_store.py — ベクトル検索

```python
class VectorStore:
    """ChromaDB ベースのベクトルストア + BM25 ハイブリッド検索。
    ONNXMiniLM_L6_V2 埋め込み、cosine類似度。
    統合スコア = vector * 0.6 + bm25 * 0.4"""
    def add(self, entry: dict) -> None
    def update(self, entry: dict) -> None
    def delete(self, eid: str) -> None
    def search(self, query: str, max_results: int = 3, min_score: float = 0.2) -> list[dict]
    def clear(self) -> None
    def count(self) -> int
```

SemanticStore が内部で VectorStore を利用する。

## データフロー

```mermaid
sequenceDiagram
    participant EB as Global EventBus
    participant MGR as MemoryManager
    participant SEN as sensory
    participant STM as short_term
    participant LTM as long_term

    alt ユーザー入力
        EB-->>MGR: MessageEvent(content, direction=request, user_identity)
        MGR->>SEN: store_raw(content)
        MGR->>MGR: pending_dict[session_id].append((content, user_identity))
        MGR->>EB: TimerTick → flush → InputReady(content, user_identity)
        MGR->>EB: InterruptEvent(session_id)

        Note over EB,STM: PlanningManager が Plan 決定後に FlowExecutor が add_turn
        EB-->>MGR: (FlowExecutor) short_term.add_turn("user", content)
    else 自発発話トリガー
        EB-->>MGR: TimerTick（pending なし）
        Note over MGR: _voice_active が空でなければ Proactive 抑制
        MGR->>EB: publish InputReady(content="", context={from_timer: True})
    else 音声録音中
        EB-->>MGR: MessageEvent(msg_type=voice_indicator, content="true"/"false")
        MGR->>MGR: _voice_active 更新（sensory/pending非保存）
    else クライアント再接続
        EB-->>MGR: ClientSessionEvent(action=connected)
        MGR->>EB: InputReady(content="", context={system_event, offline_duration})
    end

    Note over STM,LTM: 応答後
    MGR->>STM: (FlowExecutor) short_term.add_turn("assistant", response)
```

## EventBus 購読

| イベント | ハンドラ | 処理 |
|----------|----------|------|
| `MessageEvent` | `_on_message_event` | sensory.store_raw + pending保存（direction=request / event, msg_type=chat / system）。msg_type=voice_indicator は制御信号として別処理（sensory/pending非保存、_voice_active 更新） |
| `TimerTick` | `_on_timer_tick` | pending pop → InputReady + InterruptEvent または proactive InputReady |
| `ClientSessionEvent` | `_on_client_session_event` | 再接続時に escalation InputReady を発行 |

MemoryManager は **Completed イベントを購読しない**。
ContextWindow 圧縮は LLMContextWindowManager（iris/llm/context.py の `LLMContextWindowManager`）が担当する。

### publish するイベント

| イベント | タイミング | フィールド |
|----------|-----------|-----------|
| `InputReady` | 入力確定時 / TimerTick / 再接続時 | content, session_id, user_identity, context |
| `InterruptEvent` | 入力確定時 | session_id |

---

## TODO: 記憶改善ロードマップ

以下は 2024-2026 年の最新研究に基づく改善候補。
各項目に参考論文と優先度を記載。

### P1: 感情 arousal を重要度スコアリングに統合

**現状**: `DefaultImportanceScorer` がキーワード頻度ベース。limbic と記憶系が疎結合。
**改善**: `short_term/scorer.py` に limbic の `CompanionEmotion` を注入し、arousal スコアを重みに加算。`store("episodic", ...)` 時に limbic 感情状態をメタデータ付与。
**根拠**: LUFY (2025) — 感情 arousal・驚き（perplexity）・LLM重要度推定・検索頻度の6指標を学習重みで統合。感情的にengagingな記憶がユーザー満足度を大幅向上。
**実装コスト**: 低（既存 limbic からのデータ取得 + scorer へのフィールド追加のみ）

### P2: 矛盾検出 Write Gate

**現状**: `SemanticStore.add()` で重複チェックはあるが、矛盾する情報の検出なし。
**改善**: 格納前に既存エントリとの意味的重複＋論理矛盾をチェック。矛盾時は古いエントリを `superseded` フラグで無効化（物理削除しない）。
**根拠**: MemoryOS (2026) — Deterministic Write Gate が格納前に意味的重複と論理矛盾を検出。temporal versioning で bi-temporal model（event_time + transaction_time）を導入。
**実装コスト**: 中（ベクトル類似度チェック + LLM判定の組み合わせ）

### P3: セグメント単位のメモリ粒度

**現状**: ターン単位（発話1回 = 1メモリ）。
**改善**: `add_turn()` 時に発話を意味的セグメントに分割。既存の `_topics` を境界検出に活用。
**根拠**: SECOM (ICLR 2025) — セグメント単位（トピックで意味的にまとまった区块）がターン単位・セッション単位よりも高い検索精度を達成。
**実装コスト**: 中（セグメント境界検出ロジックの追加）

### P4: 事前推論格納（Pre-storage Reasoning）

**現状**: `flush()` 時に短期→長期へ即時変換。圧縮時に文脈丢失のリスク。
**改善**: `flush()` 時にLLMを使ってセグメントを3カテゴリ（事実的・体験的・主観的）に分類してから格納。既存エントリとの矛盾検出を格納前に実行。
**根拠**: PREMem (EMNLP 2025) — 格納時に3カテゴリ分類＋記憶進化パターン（拡張・変換・矛盾・確認）を追跡。小規模モデルでも大規模モデルに匹敵する精度を達成。
**実装コスト**: 中（consolidation パイプラインに LLM コール追加）

### P5: 双時間版本番管理

**現状**: タイムスタンプは格納時のみ（`base.py` の `timestamp` 1つ）。
**改善**: `ContentBlock` / エピソードエントリに `event_time`（事象発生時刻）フィールド追加。`GoalStore` の `LongTermGoal` にも適用。
**根拠**: MemoryOS (2026), memv (2026) — event_time + transaction_time の二重記録が標準化。時間推理の基盤として不可欠。
**実装コスト**: 低（フィールド追加 + 既存エージング処理への影響は小）

### P6: タイムライン型検索

**現状**: 個別メモリの検索。記憶間の因果関係・時系列関係なし。
**改善**: `EpisodicStore` のエントリ間に `caused_by` / `led_to` リンクを追加。検索時に個別エントリではなく関連タイムラインチェーンを返す。古い記憶も削除しない（変化の文脈として重要）。
**根拠**: THEANINE (NAACL 2025) — 記憶間の時系列＋因果関係で有向グラフを構築し、完全なタイムラインを検索。古い記憶も削除しない（変化の文脈として重要）。
**実装コスト**: 高（グラフ構造の追加 + 検索ロジック大幅変更）

### P7: 予測誤差ベースの抽出

**現状**: 全入力を格納。
**改善**: `flush()` 時にLLMに入力を予測させて、残差（予測誤差）が高いもののみ格納。記憶予算を本質的に新しい情報に集中。
**根拠**: memv (2026) — モデルが予測できなかった情報のみを記憶として抽出。記憶予算を効率化。小規模モデル向き（Ollama運用のIrisに適合）。
**実装コスト**: 高（consolidation 毎に LLM 予測ステップ追加）

### 実装順序

```
P5 (双時間版) → P1 (感情統合) → P2 (Write Gate) → P3 (セグメント粒度)
→ P4 (事前推論) → P7 (予測誤差) → P6 (タイムライン)
```

P5 は他全ての基盤变为、P1 は Iris 固有の強み（limbic 既存）なので最優先。P7 は LLM コールコストが増えるため、最後に検討。
