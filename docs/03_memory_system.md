# 記憶システム

## 記憶の削除

Iris起動中に `/memory-clear` コマンドで以下の全記憶を一度に削除できます：
- エピソード記憶 (`memory/episodes.jsonl`)
- 意味記憶 (`memory/semantic.jsonl` + ChromaDBベクトルストア)

構造記憶 (`memory/iris_profile.md`) は削除されず維持されます。

## 4階層記憶アーキテクチャ

| 記憶種別 | 保存先 | 内容 | 上限 | 取得方法 |
|---------|--------|------|------|---------|
| 構造記憶 | memory/iris_profile.md | Iris自身の認識（自己紹介、capability一覧、行動ルール）※話し方・性格は動的管理（別JSON） | 2KB | 常に全量読み込み |
| 作業記憶 | コンテキストウィンドウ | 現在の会話、実行中タスク | セッション内 | 自然消滅 |
| エピソード記憶 | 日次サマリーファイル | 「今日のセッション概要」 | 30エントリ | 全量読み込み（5KB上限） |
| 意味記憶 | ChromaDB + BM25全文検索 | 教訓、ユーザー好み、注意点 | 100エントリ | ハイブリッド検索（最大3件） |
| 手続き記憶 | ファイル or DB | 頻出ワークフローのテンプレート（再利用可能な手順） | 未定（蓄積次第） | 類似タスク検出時に注入 |

## 記憶の流れ

```
1. セッション中
   → 作業記憶（コンテキスト）のみ使用

2. セッション終了時（Reflexion）
   → エピソード記憶に日次サマリーを追記
   → 教訓を抽出し意味記憶に保存（類似エントリと重複チェック）
   → 頻出ワークフローを検出した場合は手続き記憶に保存
   → プロジェクト構造やcapabilityに変更があれば memory/iris_profile.md を更新

3. 次回セッション開始時
   → memory/iris_profile.md を全量読み込み（構造記憶）
   → 直近のエピソード記憶を読み込み
   → 現在の文脈に関連する教訓を意味記憶からRAG検索
   → これらをシステムプロンプトに注入
```

## 意味記憶: ハイブリッド検索設計

```python
# 教訓エントリの構造
{
    "id": "lesson_001",
    "type": "lesson",          # lesson | preference | warning
    "content": "ファイル書き込み前に存在確認が必要",
    "tags": ["file_ops", "error"],
    "timestamp": "2026-05-11",
}

# 検索方式: ハイブリッド検索（ベクトル類似度 + BM25全文検索）
#   ChromaDB ONNX MiniLM: 意味的類似性（384次元ベクトル、組み込み、追加DL不要）
#   BM25:                 キーワード一致（コード断片・固有名詞に有効）
#   統合スコア: weight_vector * 0.6 + weight_bm25 * 0.4

# max_results=3, min_score=0.2
# 上限100エントリ、超過時は古いものから削除
```

### 実装: `memory/vector_store.py`

- `VectorStore` — ChromaDB PersistentClient + ONNXMiniLM_L6_V2 組み込み埋め込み
- `_bm25_search()` — BM25 OKAPI アルゴリズム（IDF + TF正規化）
- `search()` — ベクトル検索 + BM25 の統合スコアでソート
- ChromaDB 1.5.9 以上、ONNXランタイムはpip依存関係に含まれず（ChromaDB内蔵）

### ストアインターフェース: `memory/stores.py`

各記憶ストアは `Protocol` クラス（構造的部分型付け）でインターフェースが定義されている。
新しいストアを追加する場合はこれらのProtocolに準拠することで、既存コードとの結合性を保証する。

| Protocol | 必須メソッド |
|----------|-------------|
| `AgentsMdStoreProtocol` | `load()`, `update(new_content)` |
| `EpisodicStoreProtocol` | `add(summary)`, `get_recent(n)`, `clear()` |
| `SemanticStoreProtocol` | `add(entry)`, `search(query, max_results)`, `clear()` |

## 手続き記憶設計（将来拡張）

```python
# 手続きエントリの構造（保存先は未定: ファイル or DB）
{
    "id": "procedure_001",
    "trigger": "ファイル作成前に存在確認が必要な状況",
    "steps": [
        "Test-Path で存在確認",
        "存在しなければエラーを返す、存在すれば上書き確認"
    ],
    "frequency": 5,            # 使用回数
    "last_used": "2026-05-11",
    "related_tags": ["file_ops", "safety"]
}

# 注入条件: 現在のタスクタグと手続き記憶の関連タグの一致度が閾値を超えた場合
# 上限と削除戦略はエピソード蓄積後に決定
```
