# Iris 設計改善 実装計画

## Phase1: LLMBridge.chat() に model パラメータ追加 → set_model() 副作用排除

### 変更ファイル
- `core/llm_bridge.py`
- `core/context.py`
- `core/cli.py`

### 手順

#### Step1: `core/llm_bridge.py` — `chat()` に `model` パラメータ追加

```python
def chat(
    self,
    messages: list[dict],
    model: str | None = None,  # ← 追加
    ...
) -> dict:
    effective_model = model or self.model_name  # 指定時だけ上書き
```

#### Step2: `core/context.py` — `_generate_summary()` のモデル切替を削除

変更前:
```python
def _generate_summary(self, messages, instructions=""):
    ...
    prev_model = self.llm.model_name
    if self.fast_model:
        self.llm.set_model(self.fast_model)
    try:
        resp = self.llm.chat(messages=[...], temperature=0.3, max_tokens=500, keep_alive="0")
        return resp["message"].get("content", "").strip()
    finally:
        if self.fast_model:
            self.llm.set_model(prev_model)
```

変更後:
```python
def _generate_summary(self, messages, instructions=""):
    ...
    resp = self.llm.chat(
        messages=[...],
        model=self.fast_model,  # ← model パラメータで直接指定
        temperature=0.3,
        max_tokens=500,
        keep_alive="0",
    )
    return resp["message"].get("content", "").strip()
```

`self.fast_model` フィールドは ContextManager に保持したまま、LLM呼出時に model パラメータとして渡すだけにする。

#### Step3: `core/cli.py` — `_classify_input()` のモデル切替を削除

変更前:
```python
def _classify_input(llm: LLMBridge, user_input: str, fast_model: str) -> str:
    prev = llm.model_name
    llm.set_model(fast_model)
    try:
        resp = llm.chat(messages=[...], temperature=0, max_tokens=10)
        ...
    finally:
        llm.set_model(prev)
```

変更後:
```python
def _classify_input(llm: LLMBridge, user_input: str, fast_model: str) -> str:
    resp = llm.chat(
        messages=[...],
        model=fast_model,  # ← model パラメータで直接指定
        temperature=0,
        max_tokens=10,
    )
    ...
```

#### Step4: `cli.py` — model 切替ロジック（`use_fast` 分岐）は現状維持

`cli.py:299-320` の `self.llm.set_model(...)` 呼び出しは、セッション全体で使うモデルを切り替える正規の用途。これは維持する。

---

## Phase2a: ToolExecutionEngine 抽出

### 新規ファイル
- `core/tool_executor.py`

### 変更ファイル
- `core/executor.py`
- `core/cli.py`

### Step1: ToolExecutionEngine の作成

`Executor._run_react()` と `cli.py:413-454` の共通ロジックを抽出。

```python
# core/tool_executor.py
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.llm_bridge import LLMBridge
    from capabilities.registry import CapabilityRegistry

DEFAULT_MAX_TURNS = 3


class ToolExecutionEngine:
    """Tool Call の実行と必要に応じた第2LLM呼出を共通化"""

    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.llm = llm
        self.registry = registry

    def execute_tool_calls(
        self,
        messages: list[dict],
        system_prompt: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.5,
    ) -> list[dict]:
        """messages 内の tool_calls をすべて実行し、結果を messages に追跡して返す。"""
        last = messages[-1]
        if not last.get("tool_calls"):
            return messages

        for tc in last["tool_calls"]:
            func_name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            result = self.registry.execute(func_name, **args)
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": result,
            })
        return messages

    def should_follow_up(self, tool_results: list[tuple[str, str]]) -> bool:
        """Tool 実行結果にエラーが含まれるか → 第2LLM呼出が必要か判定。"""
        for name, result in tool_results:
            if len(result) > 200 or any(
                w in result.lower() for w in ["error", "fail", "exception", "traceback"]
            ):
                return True
        return False

    def run_react(
        self,
        system_prompt: str,
        user_message: str,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tokens: int = 1000,
        temperature: float = 0.5,
        on_token: Callable[[str], None] | None = None,
    ) -> dict:
        """ReAct ループ: LLM呼出 → Tool実行 → 必要に応じて再LLM → 応答を返す。"""
        ctx: list[dict] = [{"role": "user", "content": user_message}]
        full_system = [{"role": "system", "content": system_prompt}] if system_prompt else []
        messages_base = full_system.copy()

        for turn in range(max_turns):
            resp = self.llm.chat(
                messages=messages_base + ctx,
                tools=self.registry.list_tools(),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = resp["message"]
            ctx.append(msg)

            if msg.get("tool_calls"):
                ctx = self.execute_tool_calls(ctx, system_prompt)
                # 最終ターンでなければ再LLM呼出
                if turn < max_turns - 1:
                    final = self.llm.chat(
                        messages=messages_base + ctx,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        on_token=on_token,
                    )
                    msg = final["message"]
                    ctx.append(msg)

            content = msg.get("content", "").strip()
            if content:
                return {"message": msg, "messages": ctx}

        return {"message": {"role": "assistant", "content": "(completed with no output)"}, "messages": ctx}
```

### Step2: Executor が ToolExecutionEngine を使うように変更

```python
# core/executor.py
class Executor:
    def __init__(self, llm: LLMBridge, registry: CapabilityRegistry):
        self.engine = ToolExecutionEngine(llm, registry)

    def execute_plan(self, plan, user_input, personality_name="Iris", on_subtask=None) -> str:
        subtasks = plan.get("subtasks", [])
        results = []
        for i, task in enumerate(subtasks):
            name = task.get("name", f"step_{i}")
            if on_subtask:
                on_subtask(i, name)
            desc = task.get("description", "")
            is_last = (i == len(subtasks) - 1)

            step_prompt = f"...(既存のstep_prompt生成ロジック)..."

            result = self.engine.run_react(
                system_prompt=step_prompt,
                user_message=f"Execute this task: {desc}",
            )
            output = result["message"].get("content", "")
            results.append({"name": name, "output": output})

        return results[-1]["output"] if results else ""
```

### Step3: cli.py の Tool Call 処理が ToolExecutionEngine を使うように変更

`cli.py:413-454` を以下のように置き換え:

```python
if msg.get("tool_calls"):
    tool_engine = ToolExecutionEngine(self.llm, self.registry)
    ctx = [*trimmed, msg]
    ctx = tool_engine.execute_tool_calls(ctx)
    # tool_results 抽出
    tool_results = [(tc["function"]["name"],
                     ctx[-1-i]["content"])  # toolの結果は末尾から
                    for i, tc in enumerate(msg["tool_calls"])]
    for name, result in tool_results:
        console.print(f"[dim]  → {name}(...): {result[:120]}[/dim]")

    if tool_engine.should_follow_up(tool_results):
        # 第2LLM呼出
        parts.clear()
        final = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}, *ctx],
            ...
        )
        msg = final["message"]
        self.messages.append(msg)
    else:
        # 結果を直接表示
        combined = "\n\n".join(f"**{name}** result:\n{res}" for name, res in tool_results)
        msg = {"role": "assistant", "content": combined}
        self.messages.append(msg)
```

---

## Phase2b: ConversationService 抽出

### 新規ファイル
- `core/conversation.py`

### 変更ファイル
- `core/cli.py`

### 設計

`ConversationService` は以下を担当:
1. 入力分類 (`_quick_classify`, `_classify_input`)
2. モデル選択（smart/fast の決定）
3. RAG検索 (`semantic.search`)
4. システムプロンプト構築 (Personality + episodes + summary + RAG結果)
5. コンテキスト要約判定 (ContextManager.check_and_summarize)
6. ToolExecutionEngine を使った応答生成
7. Plan-and-Execute 分岐
8. 定期的な Reflection

```python
# core/conversation.py
@dataclass
class ConversationResult:
    response_message: dict
    thinking_mode: bool
    plan_mode: bool


class ConversationService:
    def __init__(self, llm, config, registry, personality, agents_md,
                 episodic, semantic, persona_profile, reflexion,
                 planner, executor, context_manager):
        ...

    def process_input(self, user_input: str, messages: list[dict],
                      thinking_mode: bool, plan_mode: bool) -> ConversationResult:
        """1ユーザー入力に対する処理を完結させる。"""
        # 1. 分類・モデル選択
        # 2. コンテキスト要約判定
        # 3. RAG検索 + システムプロンプト構築
        # 4. Plan判定 / 実行 or 通常応答生成
        # 5. Tool Call 実行
        # 6. 定期Reflection
        ...
```

### CliSession とのインターフェース

```python
class CliSession:
    def __init__(self, config, llm):
        self.conversation = ConversationService(...)
        self.messages: list[dict] = []

    def run(self):
        while True:
            user_input = session.prompt(...)
            result = self.conversation.process_input(
                user_input, self.messages, thinking_mode, plan_mode
            )
            # 表示のみ
            self.messages.append(result.response_message)
            console.print(Panel(Markdown(content), border_style="cyan"))
```

---

## Phase4: PersonaProfile を SemanticStore 非依存化

### 新規ファイル
- `memory/persona_data.json`

### 変更ファイル
- `memory/persona_profile.py`
- `memory/stores.py`（削減）

### 設計

PersonaProfile は SemanticStore に依存せず、以下のデータモデルで専用 JSON を管理:

```json
{
  "speech_styles": [
    {"text": "丁寧だが親しみやすい", "source": "reflection", "count": 3, "timestamp": "..."},
    {"text": "簡潔で要点重視", "source": "reflection", "count": 1, "timestamp": "..."}
  ],
  "personality_traits": [
    {"text": "慎重、好奇心旺盛", "source": "reflection", "count": 2, "timestamp": "..."}
  ]
}
```

```python
class PersonaData:
    """SemanticStore を経由しない軽量なペルソナデータ管理"""
    def __init__(self, path: str = "memory/persona_data.json"):
        self.path = Path(path)
        self._data: dict = self._load()

    def add_entry(self, category: str, text: str, source: str):
        entries = self._data.setdefault(category, [])
        # 類似テキストがあればcount++, なければ新規追加
        ...

    def get_top(self, category: str, n: int = 3) -> list[dict]:
        entries = self._data.get(category, [])
        return sorted(entries, key=lambda e: e.get("count", 1), reverse=True)[:n]
```

### PersonaProfile への統合

```python
class PersonaProfile:
    def __init__(self, store: AgentsMdStore, persona_data: PersonaData):
        self.store = store
        self.persona_data = persona_data
        ...

    def _add_entry(self, category: str, text: str, source: str = "reflection"):
        self.persona_data.add_entry(category, text, source)

    def get_speech_style(self):
        entries = self.persona_data.get_top("speech_styles", 2)
        return "\n".join(f"- {e['text']}" for e in entries)
```

---

## Phase5: VectorStore スレッドセーフ対応

### 変更ファイル
- `memory/vector_store.py`

`threading.Lock` を追加し、add / update / clear / search / _rebuild_bm25 で保護:

```python
import threading

class VectorStore:
    def __init__(self, path: str = "memory/chroma_db"):
        ...
        self._lock = threading.Lock()

    def add(self, entry: dict):
        with self._lock:
            self._bm25_dirty = True
            ...

    def search(self, query, max_results=3, min_score=0.2):
        with self._lock:
            if self._bm25_dirty:
                self._rebuild_bm25()
            ...
```

---

## Phase6: Config 二重パース解消

### 変更ファイル
- `core/config.py`
- `main.py`

### Step1: Config に model_names プロパティ追加

```python
class Config(BaseModel):
    @property
    def model_names(self) -> list[str]:
        names = [self.model.smart_model]
        if self.model.fast_model:
            names.append(self.model.fast_model)
        if self.model.draft_model:
            names.append(self.model.draft_model)
        return names
```

### Step2: `main.py` のパース重複を解消

`_ensure_config_models` が dict の代わりに Config を受け取るように変更:

```python
def run():
    config_path = PROJECT_ROOT / "config.yaml"
    _restart_ollama()

    # yaml は Config.load() だけが読む
    config = Config.load(str(config_path))

    if not _ensure_config_models(config):
        sys.exit(1)

    llm = LLMBridge(
        model_name=config.model.smart_model,
        ...
    )

def _ensure_config_models(config: Config) -> bool:
    _stop_config_models(config)  # Config インスタンスを受け取るように
    time.sleep(0.5)
    for name in config.model_names:
        if not _ensure_model_pulled(name):
            return False
    return True
```

### Step3: `_stop_config_models` も Config インスタンスに

```python
def _stop_config_models(config: Config):
    for name in config.model_names:
        try:
            subprocess.run(["ollama", "stop", name], capture_output=True, timeout=10)
        except Exception:
            pass
```

これで `main.py` から `import yaml` と生の yaml.safe_load を削除可能。

---

## テスト方針

各 Phase の実装後、以下を確認:
1. `python main.py` が起動すること
2. 通常の会話（greeting/simple/qa/tool/complex 各シナリオ）が動作すること
3. `/compact` コマンドが動作すること
4. Plan mode が動作すること
5. Tool Call（ファイル読み書き等）が動作すること

各Phaseは独立しているため、途中で問題があってもそのPhaseだけを修正/ロールバック可能。

## 初期化・後処理

特に不要。すべての変更は後方互換性を維持する（古い `persona_data.json` が存在しない場合は自動生成）。
