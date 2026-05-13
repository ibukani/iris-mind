# MemoryManager 設計仕様

## 概要

MemoryManager は記憶操作を一元管理する高水準API。EpisodicStore・SemanticStore・VectorStore の3種類の記憶ストアを統合し、
ProactiveEngine や AgentKernel から利用される。

## 依存関係

```
MemoryManager
├── EpisodicStore (JSONL) — エピソード記憶、上限30エントリ
├── SemanticStore (JSONL + ChromaDB + BM25) — 意味記憶、上限100エントリ
└── VectorStore (ChromaDB + ONNXMiniLM) — ベクトル検索（後方互換用フォールバック）
```

MemoryManager はストアのインスタンスを受け取り、ラップする。自身は状態を持たない。

## 公開API

### 検索

```python
def search_semantic(
    query: str,
    max_results: int = 3,
) -> list[dict]
```

- SemanticStore でハイブリッド検索（ChromaDB + BM25）
- 失敗時は VectorStore にフォールバック
- 戻り値: `{"content", "tags", "type", "score", "timestamp"}` のリスト。score は 0.0〜1.0

```python
def get_user_preferences() -> list[dict]
```

- 固定クエリ "ユーザーの好み 興味 趣味" で検索
- search_semantic のラッパー、max_results=5

### 記録

```python
def add_episodic(
    content: str,
    kind: str = "user_input",
    metadata: dict | None = None,
) -> None
```

- エピソード記憶に追加
- `kind`: "user_input" | "assistant" | "proactive" | "system"
- `metadata` がある場合、content に追記して保存

```python
def add_semantic(
    content: str,
    tags: list[str] | None = None,
) -> None
```

- 意味記憶に教訓・好みとして追加

```python
def add_semantic_by_type(
    entry_type: str,
    content: str,
    tags: list[str] | None = None,
) -> None
```

- 種別付きで意味記憶に追加
- `entry_type`: "lesson" | "preference" | "warning" | "trait"

### 取得

```python
def get_recent(n: int = 3) -> list[dict]
```

- 直近 n 件のエピソード記憶を新しい順で返す
- 戻り値: `{"summary": str}` のリスト

## エラーハンドリング

全メソッドは例外を送出せず、失敗時は空リストを返すかログに警告を出力する。
これは ProactiveEngine のトリガースコアリングループが例外で中断されるのを防ぐため。

```
search_semantic 失敗 → 空リスト（ログ警告）
add_episodic 失敗 → ログ警告
```

## その他

- `_simple_score(query, content)`: 内部ユーティリティ。単純なキーワード一致スコア（0.0〜1.0）
- EpisodicStore の `add()` は `summary: str` のみ受け付ける。metadata は MemoryManager が文字列連結して対応
- SemanticStore の `add()` は `dict` を受け付ける
