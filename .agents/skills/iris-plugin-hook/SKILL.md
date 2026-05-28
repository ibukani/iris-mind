---
name: iris-plugin-hook
description: Iris プラグインへの Hook 追加ワークフロー
license: MIT
metadata:
  audience: developers
  workflow: iris-extension
---

## Purpose

既存の HookPoint に新しいハンドラを登録するとき、または新しい HookPoint を定義するときに読む。

## HookPoint 一覧

| HookPoint | 実行タイミング | シグネチャ | 用途例 |
|---|---|---|---|
| `llm.before_chat` | LLM呼出直前 | `(messages: list) -> list` | LoRAアダプタ注入、プロンプト加工 |
| `llm.after_chat` | LLM応答直後 | `(response: dict) -> dict` | 応答フィルタ、感情分析 |
| `llm.before_stream` | ストリームchunk毎 | `(chunk: str) -> str` | リアルタイムフィルタ |
| `memory.before_store` | エピソード保存前 | `(episode: Episode) -> Episode` | 感情タグ付与 |
| `memory.after_search` | 記憶検索後 | `(hits: list[SearchHit]) -> list[SearchHit]` | 検索結果リランキング |
| `agency.plan_decided` | 計画決定時 | `(plan: Plan) -> Plan` | 計画修正、制約追加 |
| `agency.before_exec` | 実行前 | `(state: ExecState) -> ExecState` | 実行状態注入 |
| `io.before_send` | 送信前 | `(msg: Message) -> Message` | 送信フィルタ |
| `io.after_receive` | 受信後 | `(msg: Message) -> Message` | 受信加工 |

## HookPriority

| レンジ | 分類 | 例 |
|---|---|---|
| 0-99 | SYSTEM | 必須システムフック |
| 100-999 | CORE | コア層フック |
| 1000-4999 | FEATURE | 機能プラグインフック |
| 5000-9999 | USER | 外部プラグインフック |

優先度の数値が小さい順に実行される。同優先度内は登録順。

## Steps

### 既存HookPointにハンドラを登録する

```python
# iris/<plugin>/hooks.py
def register_hooks(manager):
    hooks = manager.hook_registry

    def _my_before_chat(messages):
        # メッセージを加工
        return messages

    hooks.register("llm.before_chat", _my_before_chat, priority=500)
```

ルール:
- ハンドラは入力を受け取り、加工した同型のデータを返す
- 例外を投げても他のハンドラは継続実行される
- `priority` で実行順を制御する

### async ハンドラ

```python
async def _my_async_hook(data):
    await some_async_operation()
    return data

hooks.register("llm.before_chat", _my_async_hook, priority=500)
```

`HookRegistry.execute()` が自動判別する。呼び出し側が `await` する前提。

### 新しいHookPointを追加する

1. `iris/kernel/plugin/hook_points.py` に定義を追加:

```python
HOOK_POINTS: dict[str, HookPoint] = {
    ...
    "agency.plan_decided": HookPoint("agency.plan_decided", "計画決定時"),
}
```

2. 呼び出し元のコードに `execute()` を埋め込む:

```python
result = await manager.hook_registry.execute("agency.plan_decided", plan)
```

3. 定義を呼び出すPlugin側の `hooks.py` にハンドラを登録:

```python
hooks.register("agency.plan_decided", _on_plan_decided, priority=1000)
```

## Rules

- ハンドラは入力データを破壊せず、新しいデータを返すこと
- 例外はログ出力のみで握り潰される。後続ハンドラには影響しない
- `HookRegistry.execute()` は async、`execute_sync()` は sync
- 新しいHookPointは `HOOK_POINTS` dict に必ず登録すること
- HookPoint名は `.` 区切りの命名規則（`layer.action`）を守る
- priority は `HookPriority` の定数を使用すること
