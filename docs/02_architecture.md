# Iris アーキテクチャ

## 全体構造

```
┌─────────────────────────────────────────────────────┐
│                 Personality Layer                     │
│  思考モードOFF: Neuro-sama風の高速会話                │
│  思考モードON:  深い推論・コード生成                  │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│          ContextManager (ContextLayer)                │
│  会話Compaction（要約 + 最新メッセージ保持）         │
│  自動 compaction_threshold 判定                      │
│  手動 /compact コマンド                              │
│  base_model 使用で軽量LLM要約                        │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                Conversation Manager                  │
│  短期記憶（セッション内）                            │
│  長期記憶（ベクトルDB + サマリー）                    │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│              Task Engine                              │
│  ┌─ Simple Mode (ReAct) ─────────────────────┐      │
│  │  観察 → 思考(ツール選択) → 行動 → 観察...  │      │
│  └────────────────────────────────────────────┘      │
│  ┌─ Complex Mode (Plan-then-Execute) ────────┐      │
│  │  Planner: タスク分解 → サブゴール生成      │      │
│  │  Executor: 各サブゴールをReActで実行        │      │
│  └────────────────────────────────────────────┘      │
│  モード選択はタスク複雑度に応じて自動判定             │
│                   │                                  │
┌─────────────────────────────────────────────────────┐
│           Capability Registry (MCPベース)             │
│  全ツール・エージェント・操作を統一的に管理            │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│              Outer Loop (Reflexion)                  │
│  1. タスク完了後に振り返り                           │
│  2. 教訓を意味記憶に保存                             │
│  3. 不足capabilityの特定                             │
│  4. 自己改変モジュールへ                             │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│             Self-Modification Module                 │
│  1. 差分生成                                         │
│  2. ユーザー承認                                     │
│  3. サンドボックステスト                             │
│  4. Capability Registry に登録                       │
└─────────────────────────────────────────────────────┘
```

## 自動モデル切替（タスク複雑性ベース）

`config.yaml` の `models` リストで base / smart の2ロールを定義し、タスクの複雑性に応じてモデルを自動選択する。

### 複雑性判定フロー

```
User input
  │
  ├─ _compute_complexity_score()  (ヒューリスティックスコアリング)
  │   入力長・文数・コードブロック・ツールヒント・多段トリガーを加算
  │
  ├─ LOW  (score < 2)   → base model, ツールなし
  │   挨拶・短いQ&Aなど
  │
  ├─ MEDIUM (score 2-3) → base model, 許可ツールあり
  │   説明・簡単なファイル操作など
  │
  └─ HIGH (score >= 4)  → smart model, 全ツール
      コード生成・複数ステップのタスクなど
```

Plan mode / Thinking mode がONの場合は常にsmart modelを使用。

### ツール権限（allowed_roles）

| ツール | base | smart |
|--------|------|-------|
| read_file / write_file / list_files | ✅ | ✅ |
| run_python / run_shell | ❌ | ✅ |
| generate_capability / modify_file / sandbox_test | ❌ | ✅ |

### エスカレーションメカニズム

base model の応答が空またはエラーの場合、自動的に smart model にエスカレーションする。

```
base model で応答
  ├─ 正常 → そのまま返す
  └─ 空/エラー → _escalate()
       ├─ base model を VRAM 解放 (keep_alive=0)  [swap_on_escalate=true時]
       └─ smart model で再試行（全ツール有効）
```

### config.yaml 設定例

```yaml
model:
  models:
    - name: qwen3.5:2b
      role: base
      max_tokens: 512
    - name: qwen3.5:9b
      role: smart
      max_tokens: 1024
  escalation:
    enabled: true
    max_retries: 1
    swap_on_escalate: true
    keep_alive_duration: "5m"
```

### 応答時間目安

| 複雑性 | 使用モデル | 目標時間 |
|--------|-----------|---------|
| LOW | base (max_tokens: 512) | ~1-2s |
| MEDIUM | base (max_tokens: 512) | ~2-5s |
| HIGH | smart (max_tokens: 1024) | ~5-10s |
| エスカレーション | base→smart | +1-2s (swap時間) |
| Plan実行 | smart + Planner | ~10-20s |

## 思考モード切替

| 状況 | モード | 応答スタイル |
|------|--------|------------|
| 日常会話・雑談 | 非思考 | 即レス、キャラ全開、軽快 |
| ユーザー意図推測 | 非思考 | パッと提案 |
| ツール呼び出し | 思考 | 計画→実行→報告 |
| コード生成・自己改変 | 思考 | ステップバイステップ |
| エラー復帰 | 思考 | 原因分析→対策 |

## ディレクトリ構成

```
my-iris/
├── core/               # エンジン本体
│   ├── __init__.py
│   ├── llm_bridge.py   # LLM抽象化層
│   ├── personality.py   # キャラクター管理
│   ├── reflexion.py     # 外側ループ
│   ├── context.py       # 会話Compaction・Prune管理
│   ├── conversation.py  # 会話オーケストレーション（複雑性判定→モデル選択→コンテキスト圧縮→RAG→プロンプト構築→Plan判定→応答生成→Tool Call→エスカレーション→Reflection）
│   ├── tool_executor.py # Tool Call実行エンジン（Executor/CliSession共通利用）
│   ├── cli.py           # CliSession (薄いUI層、会話ロジックはConversationService委譲。Ollama起動はmain.pyに一元化)
│   ├── commands.py      # コマンド処理
│   ├── executor.py      # Plan-and-Execute サブタスク実行
│   ├── planner.py       # タスク分解エンジン
│   └── config.py        # 設定管理
├── capabilities/        # 機能モジュール
│   ├── __init__.py
│   ├── registry.py      # Capability Registry
│   ├── file_ops/        # ファイル操作
│   ├── code_exec/       # コード実行
│   └── self_mod/        # 自己改変
├── memory/              # 記憶管理
│   ├── __init__.py
│   ├── stores.py        # 記憶ストア定義
│   ├── vector_store.py  # ベクトルDB + BM25（スレッドセーフ）
│   ├── persona_profile.py # ペルソナ管理
│   └── persona_data.py  # ペルソナデータ（専用JSON、SemanticStore非依存）
├── docs/                # ドキュメント
├── config.yaml          # 設定ファイル
├── memory/data/iris_profile.md  # 構造記憶（上限2KB）
└── main.py              # エントリーポイント
```
