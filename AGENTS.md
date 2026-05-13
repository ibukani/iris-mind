# Iris プロジェクトルール（コーディングエージェント向け）

## プロジェクト概要
Iris は自律的に行動・進化できるAIアシスタント。Python製でOllama上で動作する。baseモデル（デフォルト: qwen3.5:2b）が大部分のタスクを処理し、複雑なタスクのみsmartモデル（デフォルト: qwen3.5:9b）にエスカレーションする2層構成。

## 重要な用語の区別
- **Iris** → このプロジェクトで製作中のAI（作る対象）
- **コーディングエージェント** → プロジェクトを支援するAI（あなた = 現在の会話相手）

## ディレクトリ構成
- `core/` → エンジン本体（config, llm_bridge, personality, reflexion, conversation, tool_executor, planner, executor, commands, cli）
- `capabilities/` → 機能モジュール（file_ops, code_exec, self_mod など）
- `memory/` → 記憶管理（stores.py, vector_store.py, persona_profile.py, persona_data.py, data/iris_profile.md）
- `docs/` → 設計ドキュメント
- `.agents/` → コーディングエージェント用コンテキスト（context.md, project.md, tasks.md）
- `AGENTS.md` → プロジェクトルール（このファイル）
- `config.yaml` → Irisの設定ファイル
- `main.py` → エントリーポイント（CLIループ）

## コンポーネント間依存関係
```
main.py
  ├── core/config.py        (pydantic BaseModel, yaml読込)
  ├── core/llm_bridge.py    (ollama.Client ラッパー)
  ├── core/personality.py    (システムプロンプト構築)
  ├── core/reflexion.py      (LLMに内省させる外側ループ)
  ├── core/context.py        (会話Compaction・Prune管理)
  ├── core/cli.py            (CliSession: ContextManager使用)
  ├── core/commands.py       (コマンド処理)
  ├── core/conversation.py    (会話オーケストレーション: 分類→モデル選択→コンテキスト→RAG→応答生成→ToolCall→Reflection)
  ├── core/planner.py        (タスク分解)
  ├── core/executor.py       (サブタスク逐次実行)
  ├── core/tool_executor.py  (Tool Call実行共通基盤)
  ├── memory/stores.py       (AgentsMdStore, EpisodicStore, SemanticStore)
  │     └── memory/vector_store.py (ChromaDB + BM25 ハイブリッド検索、スレッドセーフ)
  ├── memory/persona_data.py (ペルソナデータ専用JSON管理)
  └── capabilities/registry.py (動的モジュール発見・ツール登録)
        ├── capabilities/file_ops/server.py
        ├── capabilities/code_exec/server.py
        └── capabilities/self_mod/server.py
```

## Iris の記憶体系
- `memory/data/iris_profile.md`: Irisの構造記憶（自己認識用、上限2KB固定）※話し方・性格は含まず、別JSONで動的管理
- EpisodicStore: JSONLベースの作業記憶（上限30エントリ、古いものをマージ圧縮）
- SemanticStore: JSONL永続化 + ChromaDB + BM25 ハイブリッド検索（上限100エントリ）
- VectorStore: ONNXMiniLM_L6_V2 埋め込み、cosine類似度、統合スコア = vector*0.6 + bm25*0.4

## capability の追加ルール
1. `capabilities/<name>/server.py` に配置
2. `register(registry: CapabilityRegistry)` 関数をエクスポート
3. `@registry.register_func(...)` デコレータでツール定義
4. `__init__.py` を各パッケージに配置（必須）
5. `allowed_roles` パラメータで利用可能なモデルロールを制限（デフォルトは全てのロールで利用可）
6. 新しいcapabilityを追加したら `memory/iris_profile.md` の「My Capabilities」セクションも更新する
7. テンプレート化されたワークフローは `.agents/skills/capability-pattern/SKILL.md` を参照（`skill` ツールでロード可能）

## ドキュメント更新
機能変更時のドキュメント更新手順は `.agents/skills/doc-sync/SKILL.md` を参照（`skill` ツールでロード可能）
- 設計ドキュメント (`docs/*.md`)
- 構造記憶 (`memory/data/iris_profile.md`)
- プロジェクトルール (`AGENTS.md`)
- エージェントコンテキスト (`.agents/*.md`)
- Skills (`.agents/skills/*/SKILL.md`)

## コーディング規約
- 変更差分はユーザーに提示→承認を得てから適用
- lint/typecheck は必須
- 既存のコードスタイル・パターンに従う（インポート順、型ヒント、docstring等）
- 新機能追加時は既存のcapabilityパターンを参考にする
- Python 3.13+ の型ヒントを積極的に使用
- コメントは最小限に

## lint / typecheck コマンド
```powershell
ruff check .                          # lint
ruff format --check .                 # format check
ruff check --fix .                    # lint + auto-fix
mypy .                                # type check
mypy --install-types                  # 型スタブ初回インストール
```
※ ruff / mypy の設定は `pyproject.toml` に集約済み

## 自動モデル切替 動作ルール
- `config.yaml` の `fast_model` が設定されている場合、自動モデル切替が有効になる
- 分類は2段階: (1) キーワードフィルタ (2) 小モデルでLLM分類（不明時のみ）
- シナリオは `greeting/simple/qa/tool/complex` の5種類
- `tool/complex` は大モデル、それ以外は小モデルを使用
- mode が deep/stepwise の場合は常に大モデルを使用（auto は複雑性判定に従う）
- 小モデルにはツール定義を渡さない（ツール呼び出し不可のため）
- 会話履歴は `context_window`（トークン数）を超えた場合、`compaction_threshold` に基づき自動要約（ContextManager）
- 要約は `## 会話の経緯` としてシステムプロンプトに注入。`/compact` コマンドで手動トリガー可能
- 要約時は `fast_model` を使用（コンパクション専用LLM呼び出しを高速化）


## git コミットルール
- 1タスク完了ごとに必ずgitコミットを行う
- コミットメッセージは日本語で、変更内容が一目でわかるように書く
  - 良い例: 「feat: ファイル検索capabilityを追加」「fix: ReflexionのJSONパースエラーを修正」「docs: アーキテクチャ図を最新化」
- コード変更とドキュメント更新は同一コミットに含める（不整合防止）

## 技術スタック
- Python 3.13+, ollama, pydantic, pyyaml, rich, prompt_toolkit
- ChromaDB + ONNX（ベクトル検索）
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
- 使用モデル: Qwen3.5:9b（デフォルト）、Ollama経由
