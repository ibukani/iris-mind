# Iris プロジェクトルール（コーディングエージェント向け）

## プロジェクト概要
Iris は自律的に行動・進化できるAIアシスタント。Python製でOllamaまたはOpenRouter上で動作する。モデル構成は柔軟で、1モデルのシングルモード（全処理に同一モデルを使用）と、複数モデルのマルチモード（roleベースの使い分け）を設定可能。

## 重要な用語の区別
- **Iris** → このプロジェクトで製作中のAI（作る対象）
- **コーディングエージェント** → プロジェクトを支援するAI（あなた = 現在の会話相手）

## ディレクトリ構成

```
.iris/
├── config/
│   └── personality_default.md   ← 静的テンプレート（git追跡）
└── data/
    ├── iris_profile.md           ← Irisの構造記憶（自己認識用、上限2KB固定）
    ├── episodes.jsonl            ← エピソード記憶
    ├── semantic.jsonl            ← 意味記憶
    ├── persona_data.json         ← 話し方・性格（動的管理）
    └── chroma_db/                ← ChromaDBベクトルストア

adapters/                         ← 外部UI層（CLI, API, GUI）
├── cli/                          ← CLIアダプター（実際の対話インターフェース）
└── __init__.py

iris/                             ← アプリケーションコア
├── kernel/                       ← ドメイン層（EventBus, AgentState, Config,
│                                  MemoryManager, ProactiveEngine, AgentKernel,
│                                  ConversationService, Reflexion, ContextManager,
│                                  ToolExecutionEngine, KernelFactory）
├── llm/                          ← LLM通信（LLMBridge, OllamaProvider, OpenRouterProvider）
├── memory/                       ← 記憶管理（stores, vector_store, persona）
├── capabilities/                 ← ツール実行（registry + 8 tools）
├── commands/                     ← コマンド処理（CommandHandler）
├── personality/                  ← プロンプト管理（Personality）
└── __init__.py

docs/                             ← 設計ドキュメント
.agents/                          ← コーディングエージェント用コンテキスト
config.yaml                       ← Irisの設定ファイル
main.py                           ← エントリーポイント
```

## コンポーネント間依存関係（ヘキサゴナルアーキテクチャ）

```
adapters/          ──→ iris/kernel/   ──→ iris/llm/, iris/memory/, iris/capabilities/
(UI層)               (ドメイン層)         (インフラ層)
```
- `adapters/` は `iris/` に依存するが、逆方向の依存はディレクトリ構造で物理禁止
- `iris/kernel/` は純粋なビジネスロジックに閉じ、外部サービスは kernel 外から注入

## Iris の記憶体系
- `.iris/data/iris_profile.md`: Irisの構造記憶（自己認識用、上限2KB固定）※話し方・性格は含まず、別JSONで動的管理
- EpisodicStore: JSONLベースの作業記憶（上限30エントリ、古いものをマージ圧縮）
- SemanticStore: JSONL永続化 + ChromaDB + BM25 ハイブリッド検索（上限100エントリ）
- VectorStore: ONNXMiniLM_L6_V2 埋め込み、cosine類似度、統合スコア = vector*0.6 + bm25*0.4

## capability の追加ルール
1. `iris/capabilities/<name>/server.py` に配置
2. `register(registry: CapabilityRegistry)` 関数をエクスポート
3. `@registry.register_func(...)` デコレータでツール定義
4. `__init__.py` を各パッケージに配置（必須）
5. `allowed_roles` パラメータで利用可能なモデルロールを制限（デフォルトは全てのロールで利用可）
6. 新しいcapabilityを追加したら `.iris/data/iris_profile.md` の「My Capabilities」セクションも更新する
7. テンプレート化されたワークフローは `.agents/skills/capability-pattern/SKILL.md` を参照（`skill` ツールでロード可能）

## ドキュメント更新
機能変更時のドキュメント更新手順は `.agents/skills/doc-sync/SKILL.md` を参照（`skill` ツールでロード可能）
- 設計ドキュメント (`docs/*.md`)
- 構造記憶 (`.iris/data/iris_profile.md`)
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

## モデル構成
- 設定されたモデル数によって動作モードが自動判定される
- **シングルモード**（`models` が1つ）: 全処理にその1モデルを使用
- **マルチモード**（`models` が2つ以上）: `get_model(role)` で role ベースのモデル選択
  - 未知の role が指定された場合は `models[0]` にフォールバック
- `config.yaml` の `model.provider` で Ollama / OpenRouter を切り替え可能
- 会話履歴は `context_window`（トークン数）を超えた場合、`compaction_threshold` に基づき自動要約（ContextManager）
- 要約は `## 会話の経緯` としてシステムプロンプトに注入。`/compact` コマンドで手動トリガー可能
- 要約時のモデルは `ModelConfig.get_model("default")` を使用（単一モデルも複数モデルも同じインターフェース）


## git コミットルール
- 1タスク完了ごとに必ずgitコミットを行う
- コミットメッセージは日本語で、変更内容が一目でわかるように書く
  - 良い例: 「feat: ファイル検索capabilityを追加」「fix: ReflexionのJSONパースエラーを修正」「docs: アーキテクチャ図を最新化」
- コード変更とドキュメント更新は同一コミットに含める（不整合防止）

## 技術スタック
- Python 3.13+, ollama, httpx, pydantic, pyyaml, rich, prompt_toolkit
- ChromaDB + ONNX（ベクトル検索）
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
- 使用モデル: Qwen3.5:9b（デフォルト、Ollama/OpenRouter経由）
