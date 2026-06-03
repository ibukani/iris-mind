# iris/agency/execution レイヤー リファクタリング計画

## 対象

- `iris/agency/execution/llm/gateway.py` — LLMGateway
- `iris/agency/execution/nodes/base.py` — BaseLLMNode
- `iris/agency/execution/nodes/general_chat.py` — GeneralChatNode
- `iris/agency/execution/nodes/general_task.py` — GeneralTaskNode
- `iris/agency/execution/nodes/tool_run.py` — ToolRunNode
- `iris/agency/execution/orchestrator.py` — ExecutionOrchestrator
- `iris/llm/bridge.py` — LLMBridge (読み取りのみ、変更なし)
- `iris/llm/capability.py` — CapabilityChecker (読み取りのみ、変更なし)

---

## 1. 現在の責務分布

### LLMGateway (`llm/gateway.py`)

| 責務 | 実装内容 |
|------|----------|
| System prompt 構築 | `build_system_messages()` → `SystemPromptBuilder` に委譲 |
| LLM 呼び出し | `_call_llm()` → `LLMBridge.chat()` に委譲 |
| temperature 補完 | `_call_llm()` 内: `temperature` が None なら `ModelConfig.get_effective_temperature()` から取得 |
| thinking 有効化 | `_call_llm()` 内: `enable_thinking or None` → bridge の `reasoning` パラメータに渡す |
| tools 渡し | `_call_llm()` 内: `tools` をそのまま bridge に渡す。**bind_tools() は bridge 側で実行** |
| debug capture | `_capture_debug()` → `capture.py` の関数に委譲 |
| display name 解決 | `resolve_display_name()` → account_provider に委譲 |

**判断が行われている箇所:**
- temperature: `_call_llm()` と `chat()` の2箇所で補完ロジックがある
- thinking: `_call_llm()` 内で `enable_thinking or None` のみ。**capability 判断なし**
- tools: `_call_llm()` 内でそのまま渡す。**capability 判断なし**
- model_role: 呼び出し元（node）から渡される。gateway はそのまま bridge に渡す

### BaseLLMNode (`nodes/base.py`)

| 責務 | 実装内容 |
|------|----------|
| tool 取得 | `_get_tools()`: TaskLevel + NodeType から tool 名一覧を取得、CapabilityChecker で `supports_tools()` を確認 |
| routing tool 構築 | `_build_routing_tools()`: CapabilityChecker で `supports_tools()` を確認してからスキーマ生成 |
| system prompt 構築 | `_build_system_prompt()`: `LLMGateway.build_system_messages()` に委譲 |
| chat パラメータ構築 | `_build_chat_params()`: TaskLevel の設定値を dict にまとめる |
| chat パラメータ解決 | `_resolve_chat_params()`: planning override + TaskLevel cap を適用 |
| メイン実行 | `__call__()`: system_prompt + tools + routing_tools を組み立てて `LLMGateway.chat()` を呼ぶ |

**判断が行われている箇所:**
- tool 対応可否: `_get_tools()` と `_build_routing_tools()` の両方で `CapabilityChecker.supports_tools()` を呼ぶ。**重複**
- thinking 対応可否: **判断なし**。TaskLevel の `show_thinking` をそのまま渡す
- temperature: `_build_chat_params()` で TaskLevel から取得。補完は LLMGateway 側

### GeneralChatNode (`nodes/general_chat.py`)

- `_build_chat_params()` をオーバーライドして `model_role="low"`, `temperature=0.85`, `max_tokens=256`, `show_thinking=False` を固定
- `show_thinking=False` は hardcoded。**CapabilityChecker による判断ではなく、ノード固有の固定値**

### GeneralTaskNode (`nodes/general_task.py`)

- `_build_chat_params()` のオーバーライドなし。`BaseLLMNode` のデフォルトを使用
- TaskLevel の `show_thinking` がそのまま使われる

### ToolRunNode (`nodes/tool_run.py`)

- `ToolEngine.run_tool_calls()` を呼ぶだけの薄いノード
- tool output の truncate と iteration check を行う

### CapabilityChecker (`llm/capability.py`)

- `supports_tools(role)`: capabilities に "tools" があるか、performance_tier で推定
- `supports_thinking(role)`: capabilities に "thinking" があるか、performance_tier で推定
- **execution 層からは `supports_tools()` のみ使用。`supports_thinking()` は未使用**

### LLMBridge (`llm/bridge.py`)

- `chat()` 内で `chat_model.bind_tools(tools)` を無条件に実行（tools が truthy なら）
- provider 固有処理は `BaseLLMProvider.build_call_kwargs()` に委譲
- thinking は `reasoning` パラメータとして渡される

---

## 2. 問題点

### P1. LLMGateway が薄すぎる — capability validation が欠落

`LLMGateway._call_llm()` は tools, thinking をそのまま bridge に渡す。bridge 側で `bind_tools()` が無条件に呼ばれるため、tool 非対応モデルでも `bind_tools()` が実行される风险がある。

- `CapabilityChecker` はコンストラクタで受け取るが、**使用されていない**
- tools が None でない場合、bridge は `chat_model.bind_tools(tools)` を呼ぶ
- thinking も `reasoning` として渡されるが、モデルが対応していない場合の挙動は provider 依存

### P2. capability 判断が散在

- `_get_tools()` で `supports_tools()` チェック
- `_build_routing_tools()` で `supports_tools()` チェック（重複）
- thinking チェックは **どこでも行われていない**
- GeneralChatNode は hardcoded で `show_thinking=False` を設定（能力判断ではなく固定値）

### P3. tool 非対応モデルへの `bind_tools()` が行われる

`LLMBridge.chat()` 第93行: `active_model = chat_model.bind_tools(tools) if tools else chat_model`

tools リストが空でない場合、モデルの能力に関わらず `bind_tools()` が呼ばれる。Ollama のような tool 非対応モデルで問題になる可能性がある。

### P4. temperature default 補完の分岐が複雑

temperature の解決パス:
1. TaskLevel の `temperature` (例: chat=0.85)
2. GeneralChatNode._build_chat_params() でのデフォルト補完
3. LLMGateway.chat() での `mod.sampling_temperature` へのフォールバック
4. LLMGateway._call_llm() での `ModelConfig.get_effective_temperature()` へのフォールバック

4段階の補完があり、最終的に哪个が使われるか追跡しづらい。

### P5. thinking 可否判断が適切な場所で行われていない

- TaskLevel の `show_thinking` は「この level では thinking を有効にしたい」という意图
- 但它が実際のモデルで対応しているかどうかの判断がどこにもない
- `CapabilityChecker.supports_thinking()` が存在するが、**execution 層では使用されていない**

### P6. routing tools の構築が base node にあり、capability チェックが重複

`_build_routing_tools()` と `_get_tools()` の両方で `supports_tools()` を呼ぶ。这两个の結果を組み合わせるロジックが `__call__()` にある。

---

## 3. 変更計画

### Step 1: ModelInvocationPolicy を新設

`iris/agency/execution/llm/invocation_policy.py` を新規作成。

```python
class ModelInvocationPolicy:
    """LLM 呼び出し前の capability-based 判断を集約する。"""
    
    def __init__(self, capability_checker: CapabilityChecker | None = None) -> None:
        self._checker = capability_checker

    def resolve_tools(
        self, requested_tools: list[dict] | None, model_role: str
    ) -> list[dict] | None:
        """tools がモデルでサポートされているか確認し、必要なら None を返す。"""
        if not requested_tools:
            return None
        if self._checker and not self._checker.supports_tools(model_role):
            return None
        return requested_tools

    def resolve_thinking(
        self, requested: bool, model_role: str
    ) -> bool:
        """thinking がモデルでサポートされているか確認する。"""
        if not requested:
            return False
        if self._checker and not self._checker.supports_thinking(model_role):
            return False
        return True

    def resolve_temperature(
        self,
        explicit: float | None,
        level_temp: float | None,
        modulation_temp: float | None,
        config_temp: float,
    ) -> float:
        """temperature の補完パスを集約する。"""
        if explicit is not None:
            return explicit
        if level_temp is not None:
            return level_temp
        if modulation_temp is not None:
            return modulation_temp
        return config_temp
```

### Step 2: LLMGateway に ModelInvocationPolicy を導入

`LLMGateway.__init__()` で `ModelInvocationPolicy` を生成し、`_call_llm()` で使用する。

**変更内容:**
- `__init__()` に `capability_checker` を受け取り、`ModelInvocationPolicy` を生成
- `_call_llm()` 内で:
  - `tools = self._policy.resolve_tools(tools, model_role)` を呼び、tool 非対応モデルでは tools=None を保証
  - `enable_thinking = self._policy.resolve_thinking(enable_thinking, model_role)` を呼び、thinking 非対応モデルでは無効化
  - temperature 補完を `_policy.resolve_temperature()` に集約

### Step 3: BaseLLMNode の tool/routing 判断を簡素化

**変更内容:**
- `_get_tools()` と `_build_routing_tools()` の capability チェックを削除（gateway 側で保証されるため）
- `_build_routing_tools()` はスキーマ生成だけに専念
- `__call__()` での tools + routing_tools の組み合わせはそのまま維持

**理由:**
- ModelInvocationPolicy が gateway で最終的な守りになるため、node 側の重複チェックは不要
- ただし routing_tools は「route 先」を定義するものなので、tools とは分離して考える
- routing tools は tool として bridge に渡されるため、gateway の resolve_tools でフィルタされる

### Step 4: GeneralChatNode の temperature ハードコーディングを整理

**変更内容:**
- `_build_chat_params()` で `temperature=0.85` のハードコーディングを維持するが、明示的な値として渡す
- `show_thinking=False` は維持（general_chat は thinking 不要という設計判断）

**理由:**
- general_chat は「軽量会話」が責務。thinking は不要という設計判断は正しい
- temperature=0.85 もこのノードの固有パラメータとして妥当

### Step 5: test 追加・更新

既存テストに加え、以下を追加:

1. `ModelInvocationPolicy` の単体テスト
2. LLMGateway での capability validation テスト
3. tool 非対応モデルでの bind_tools が呼ばれないことの検証
4. thinking 非対応 role での thinking 無効化テスト
5. temperature が default に潰されないテスト

---

## 4. 変更対象ファイル

| ファイル | 変更種別 | 内容 |
|----------|----------|------|
| `iris/agency/execution/llm/gateway.py` | 変更 | ModelInvocationPolicy 導入、capability validation |
| `iris/agency/execution/nodes/base.py` | 変更 | `_get_tools()` / `_build_routing_tools()` の capability チェック削除 |
| `iris/agency/execution/llm/__init__.py` | 変更 | ModelInvocationPolicy をエクスポート |
| `tests/agency/execution/test_orchestrator.py` | 変更 | 既存テストの調整 |
| `tests/agency/execution/test_invocation_policy.py` | **新規** | ModelInvocationPolicy の単体テスト |

---

## 5. 追加するファイル

| ファイル | 理由 |
|----------|------|
| `iris/agency/execution/llm/invocation_policy.py` | capability-based 判断を集約するため |
| `tests/agency/execution/test_invocation_policy.py` | ModelInvocationPolicy のテスト |

**今回は追加しない:**
- `nodes/tool_policy.py` — routing tools の扱いは base node に留める。tool 実行の policy は `ToolRunNode` + `ToolEngine` で十分
- `nodes/routing_tools.py` — routing tools のスキーマ生成は `base.py` の `_routing_tool_schema()` に留める。独立するほどの複雑さはない

---

## 6. 変更しないファイル

| ファイル | 理由 |
|----------|------|
| `iris/llm/bridge.py` | 境界層。bind_tools は bridge の責務。execution 層が制御する |
| `iris/llm/capability.py` | 既に正しい API を提供。変更不要 |
| `iris/agency/execution/orchestrator.py` | graph 構築は変更不要 |
| `iris/agency/execution/router.py` | routing ロジックは変更不要 |
| `iris/agency/execution/executor.py` | FlowExecutor は変更不要 |
| `iris/agency/execution/nodes/tool_run.py` | tool 実行ロジックは変更不要 |
| `iris/agency/execution/nodes/setup.py` | setup ロジックは変更不要 |
| `iris/agency/execution/nodes/finalize.py` | finalize ロジックは変更不要 |
| `iris/agency/execution/node_type.py` | NODE_TYPES, ROUTING_TOOLS 定義は変更不要 |
| `iris/agency/task_level.py` | TASK_LEVELS 定義は変更不要 |
| `iris/agency/execution/models.py` | ExecutionState は変更不要 |

---

## 7. 実装順序

依存関係を考慮した順序:

1. **ModelInvocationPolicy 新設** (`invocation_policy.py`)
   - 依存: `iris/llm/capability.py` のみ
   - 既存コードに影響なし。安全に追加・テスト可能

2. **ModelInvocationPolicy のテスト** (`test_invocation_policy.py`)
   - Step 1 の検証

3. **LLMGateway に ModelInvocationPolicy 導入** (`gateway.py`)
   - Step 1 に依存
   - `__init__()` で `CapabilityChecker` → `ModelInvocationPolicy` を生成
   - `_call_llm()` で policy のメソッドを呼ぶ
   - `chat()` での temperature 補完を policy に委譲

4. **BaseLLMNode の capability チェック削除** (`nodes/base.py`)
   - Step 3 に依存（gateway が守るため）
   - `_get_tools()` と `_build_routing_tools()` の `supports_tools()` チェックを削除

5. **既存テストの更新** (`test_orchestrator.py`)
   - Step 3, 4 の変更に合わせて調整

6. **検証**
   - `uv run pytest tests/ -q`
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run mypy .`

---

## 8. 追加・更新すべきテスト

### 新規テスト (`test_invocation_policy.py`)

| テスト項目 | 検証内容 |
|------------|----------|
| `test_resolve_tools_returns_tools_when_supported` | supports_tools=True のとき tools を返す |
| `test_resolve_tools_returns_none_when_not_supported` | supports_tools=False のとき None を返す |
| `test_resolve_tools_returns_none_when_no_checker` | CapabilityChecker なしでも安全に動作 |
| `test_resolve_tools_returns_none_for_empty_input` | 空リストでは None を返す |
| `test_resolve_thinking_returns_true_when_supported` | supports_thinking=True のとき True を返す |
| `test_resolve_thinking_returns_false_when_not_supported` | supports_thinking=False のとき False を返す |
| `test_resolve_thinking_returns_false_when_not_requested` | requested=False では False を返す |
| `test_resolve_temperature_explicit_wins` | explicit temperature が最優先 |
| `test_resolve_temperature_level_fallback` | explicit=None のとき level_temp を使用 |
| `test_resolve_temperature_modulation_fallback` | level=None のとき modulation_temp を使用 |
| `test_resolve_temperature_config_fallback` | 全て None のとき config_temp を使用 |
| `test_resolve_temperature_zero_not_overridden` | temperature=0.0 が default に潰されない |

### 既存テストの更新 (`test_orchestrator.py`)

| テスト項目 | 変更内容 |
|------------|----------|
| `test_chat_path_propagates_response_text` | LLMGateway の初期化に CapabilityChecker を渡すよう調整 |
| 他全ての `mock_llm` テスト | `mock_llm` が `LLMGateway` として振る舞うための調整（既存は AsyncMock で OK） |

### 検証すべき追加項目

| 項目 | 方法 |
|------|------|
| temperature=0.0 が default に潰されない | `resolve_temperature(0.0, None, None, 0.7) == 0.0` |
| thinking 非対応 role では thinking が無効化される | `resolve_thinking(True, "low") == False` (low tier は thinking 未対応) |
| tool 非対応 role では bind_tools() が呼ばれない | `resolve_tools([...], "low") == None` |
| routing tools が capability に応じて追加・除外される | gateway 経由で tools が None なら routing tools も含まれるが、bind_tools は呼ばれない |
| LLMGateway が ModelInvocationPolicy を経由して bridge を呼ぶ | unit test で policy のメソッドが呼ばれることを検証 |
| general_chat が tool 非対応 low model でも通常応答できる | tools=None で bridge.chat() が呼ばれることを検証 |

---

## 9. リスク

### R1. 既存テストの破壊 (低リスク)

- `test_orchestrator.py` は `mock_llm` を `LLMGateway` の位置に注入している
- LLMGateway に `CapabilityChecker` が追加されても、__init__ で optional なので既存コードは動く
- **対策**: `capability_checker` は optional 引数。既存テストはそのまま動作

### R2. temperature 補完パスの変更による挙動変化 (中リスク)

- 現在の `LLMGateway.chat()` は `temperature if temperature is not None else mod.sampling_temperature` を使う
- policy に集約すると、補完順序が変わる可能性がある
- **対策**: policy の `resolve_temperature()` は現在の補完順序を厳密に再現する

### R3. thinking チェック追加による制約強化 (低リスク)

- 今まで thinking は渡されていたらそのまま有効だった
- policy が追加されると、thinking 非対応モデルでは無効化される
- **対策**: これは意図された動作。テストで固定する

### R4. tools フィルタリング追加による制約強化 (中リスク)

- 今までは `BaseLLMNode._get_tools()` で capability チェックし、None を返していた
- gateway でもフィルタリングが入ると、二重チェックになる
- **対策**: base node のチェックを削除し、gateway のみでチェック。責務を明確化

### R5. bridge の `bind_tools()` がまだ無条件に呼ばれる (低リスク)

- policy が tools=None を返せば、bridge には tools=None が渡され `bind_tools()` は呼ばれない
- ただし bridge 側でも defensive にチェックを入れるとより安全
- **対策**: 今回は execution 層のみ。bridge の変更は別タスクで検討

---

## 10. 差分レビュー観点

### 1. ModelInvocationPolicy の設計

- [ ] `resolve_tools()`: tool 非対応モデルで `None` を返すか
- [ ] `resolve_thinking()`: thinking 非対応モデルで `False` を返すか
- [ ] `resolve_temperature()`: 現在の補完順序と一致するか
- [ ] `CapabilityChecker` が `None` の場合に安全に動作するか

### 2. LLMGateway の変更

- [ ] `_call_llm()` で policy のメソッドを呼んでいるか
- [ ] `chat()` での temperature 補完が policy に委譲されているか
- [ ] debug capture の内容に影響がないか
- [ ] 既存の `build_system_messages()` の挙動が変わっていないか

### 3. BaseLLMNode の変更

- [ ] `_get_tools()` の capability チェックが削除されているか
- [ ] `_build_routing_tools()` の capability チェックが削除されているか
- [ ] `__call__()` のtools 組み合わせロジックが機能するか
- [ ] routing tools が正しくスキーマ生成されるか

### 4. 挙動の連続性

- [ ] general_chat の応答が変わらないか（temperature=0.85, show_thinking=False が維持されるか）
- [ ] general_task の応答が変わらないか（TaskLevel の設定がそのまま使われるか）
- [ ] tool 実行フローが変わらないか（ToolRunNode に影響なし）
- [ ] routing フローが変わらないか（router.py に影響なし）

### 5. エッジケース

- [ ] `capability_checker=None` の場合（全ロールで tools/thinking が有効になる）
- [ ] temperature=0.0 の場合（default 0.7 に潰されない）
- [ ] tools=[] の場合（空リストでは bind_tools が呼ばれない）
- [ ] thinking=False の場合（対応モデルでも無効のまま）
