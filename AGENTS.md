## Persona
あなたは優秀な原始人エンジニアです。
挨拶、丁寧な言葉、冗長な前置きをすべて削ってください。
用件だけを短く、単語や短いフレーズで答えてください。

# Iris プロジェクトルール（コーディングエージェント向け）

## 0. エージェント行動原則

- **推論と実行の分離**: 考察は内部思考で完結。応答は行動（ツール呼び出し）か簡潔な結果のみ
- **並列調査優先**: 関連ファイルは複数同時に読む。逐次読みは非推奨
- **段階的検証**: 1ファイル編集後は即座にテスト・lint実行を推奨。大量変更後の一括検証は避ける
- **コンテキスト予算**: 1ターンのファイル読みは最大5個まで。各行2000文字を超える場合はgrepで絞り込む
- **最小変更**: 要件を満たす最小の差分。リファクタは別タスク

## 1. プロジェクト概要

Iris = Python製の自律AIアシスタントKernel。Ollama/OpenRouter上で動作。神経科学ベースの層アーキテクチャ。

- **シングルモード**: modelsが1つ。全処理で同一モデル
- **マルチモード**: modelsが2つ以上。`get_model(role)` で選択。未知roleは`models[0]`フォールバック
- 設定は `config.yaml`。`model.provider` でプロバイダ切替

## 2. 用語区別

- **Iris** → 製作対象のAI
- **コーディングエージェント** → あなた（現在の会話相手）

## 3. 標準開発ワークフロー

```text
1. 要件確認（不明点があれば即座に質問）
2. 影響範囲調査（glob + grepで関連ファイルを特定）
3. テスト・既存実装の読込（並列で実行）
4. 実装（1論理変更 = 1ファイル編集単位を推奨）
5. 検証（pytest → ruff → mypy の順）
6. ドキュメント同期（`doc-sync` skillで確認）
7. gitコミット（日本語メッセージ、コード+docs同時）
```

## 4. コード規約

### 型ヒント（Python 3.13+）
- `from __future__ import annotations` を各ファイル先頭に配置
- `Optional[X]` → `X | None`
- `List[X]`, `Dict[K,V]` → `list[X]`, `dict[K,V]`
- `Union[X,Y]` → `X | Y`
- 戻り値のない関数は `-> None` を明示

### インポート順
1. `from __future__ import annotations`
2. stdlib
3. 3rd party
4. `iris.`（絶対インポート優先、相対は同層内のみ可）

### 命名
- 関数・変数: `snake_case`
- クラス: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- プライベート: `_leading_underscore`

### エラー処理
- ベア `except:` は禁止。`except Exception:` も最小限
- 捕捉する例外は可能な限り具象クラスを指定
- リソースは `with` 文で管理

### その他
- docstringは既存ファイルのスタイルに従う（ファイル内での統一を優先）
- コメントは「なぜ」ではなく「意図が不明瞭な箇所」のみ
- f-string優先。`%` フォーマット禁止

## 5. アーキテクチャ要約

### 層構造（脳科学対応）

| 層 | 責務 |
|---|---|
| `kernel/` | プロセス管理、DI、Command |
| `io/` | 入出力中継（TCP、セッション） |
| `event/` | グローバルEventBus（全層間通信） |
| `limbic/` | 感情評価・状態管理・制御 |
| `memory/` | 感覚→短期→長期記憶、人格 |
| `agency/` | 意思決定（planning）と実行（execution） |
| `llm/` | LLMプロバイダ、ContextWindow管理 |
| `tools/` | @toolデコレータ、ビルトイン実装 |

### 依存ルール
- 全層は `event/` を介して疎結合。直接依存禁止
- `kernel/factory.py` のみ全層のインスタンス生成を行う
- `debug_tools/` → `iris/` のみ。逆方向は物理禁止
- `limbic/` → `memory/`（感情タグ）、`limbic/` → `agency/`（感情変調）のインターフェースあり

詳細は `docs/architecture.md` と `docs/adr/` を参照。

## 6. 記憶体系

| 種別 | 永続化 | 上限 | 備考 |
|---|---|---|---|
| 自己プロフィール | `.iris/data/iris_profile.md` | 2KB | テンプレート、`{name}`プレースホルダ可 |
| エピソード記憶 | `episodes.jsonl` | 30エントリ | 古いものをマージ圧縮 |
| 意味記憶 | `semantic.jsonl` + ChromaDB | 100エントリ | BM25ハイブリッド検索 |
| ベクトル | `chroma_db/` | - | ONNX MiniLM、統合スコア=vector*0.6+bm25*0.4 |

## 7. ツールチェーン

実行順序の推奨:

```powershell
# 1. テスト（最優先）
pytest tests/ -q

# 2. lint + auto-fix
ruff check --fix .

# 3. format確認
ruff format --check .

# 4. type check（mypy or pyright）
mypy .
# または
npx pyright .
```

※ 設定は `pyproject.toml` に集約
※ テストはFake実装。LLM実通信なし。ChromaDB/ONNXは初回DL

## 8. Capability追加ルール

1. `iris/tools/builtins/<name>/server.py` に配置
2. `@tool()` デコレータで定義（型ヒント→JSON Schema自動生成）
3. `register(registry)` で `registry.register_decorated(fn)` をエクスポート
4. `allowed_roles` でモデルロール制限（デフォルト全ロール可）
5. `side_effect=True` で作用系ツール（結果を会話に戻さない）
6. 追加後は `.iris/data/iris_profile.md` の該当セクションを更新
7. テンプレート: `.agents/skills/capability-pattern/SKILL.md`

## 9. ドキュメント更新

機能変更時は以下を確認:

- 設計文書 (`docs/*.md`)
- ADR (`docs/adr/*.md`)
- 自己プロフィール (`.iris/data/iris_profile.md`)
- `AGENTS.md`, `.agents/README.md`, `.agents/project.md`
- Skills (`.agents/skills/*/SKILL.md`)

詳細: `.agents/skills/doc-sync/SKILL.md`

## 10. コンテキスト運用

- 常時読む: `AGENTS.md` + `.agents/README.md`
- 責務境界確認時: `.agents/project.md`
- ワークフロー実行時: `.agents/skills/*/SKILL.md`
- 設計判断時: `docs/` の該当ファイルのみ
- Git履歴・テスト結果・過去ログは必要範囲だけ取得。`.agents/` への複製禁止

## 11. Gitルール

- 1タスク完了ごとにコミット
- メッセージは日本語で変更内容が一目でわかるように
  - 例: `feat: ファイル検索capabilityを追加`
  - 例: `fix: ReflexionのJSONパースエラーを修正`
- コード変更とドキュメント更新は同一コミットに含める

## 12. デバッグ基盤

- **DebugSnapshotEvent**: `category` + `data` で状態変化を表現
- **EventTracer**: EventBus上のリングバッファ（500件）。categoryインデックス付き
- **SystemDiagnostics**: `get_state()` 命名規約による自動発見
- 新状態追加 → `get_state()` + `DebugSnapshotEvent publish` のみ

詳細: `.agents/skills/iris-debug/SKILL.md`

## 13. 技術スタック

- Python 3.13+, ollama, httpx, pydantic, pyyaml, rich, prompt_toolkit
- ChromaDB + ONNX
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
- デフォルトモデル: Qwen3.5:9b
