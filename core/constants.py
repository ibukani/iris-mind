"""共通定数・設定値。"""

# ── モデル関連 ──────────────────────────────────────────────
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MAX_TOKENS_FAST = 256
DEFAULT_TEMPERATURE = 0.7
DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_GPU = 0

# ── シナリオ別トークン上限 ─────────────────────────────────
MAX_TOKENS_BY_SCENARIO: dict[str, int] = {
    "greeting": 64,
    "simple": 256,
    "qa": 1024,
    "tool": 1024,
    "complex": 1024,
}

# ── シナリオ別設定 (use_fast, max_context_tokens) ───────────
SCENARIOS: dict[str, tuple[bool, int]] = {
    "greeting": (True, 256),
    "simple": (True, 512),
    "qa": (True, 1024),
    "tool": (False, 1024),
    "complex": (False, 1024),
}

# ── 分類関連 ────────────────────────────────────────────────
GREETING_WORDS = frozenset(
    {
        "hello",
        "hi",
        "bye",
        "hey",
        "thanks",
        "thank",
        "yes",
        "no",
        "good morning",
        "good evening",
        "good night",
        "おはよう",
        "こんにちは",
        "こんばんは",
        "おやすみ",
        "はい",
        "いいえ",
        "ありがとう",
        "おっす",
        "やあ",
    }
)

ENDING_WORDS = frozenset(
    {
        "終わる",
        "終わります",
        "終わり",
        "終了",
        "さようなら",
        "バイバイ",
        "またね",
        "それじゃ",
        "quit",
        "exit",
        "bye bye",
        "see you",
    }
)

TOOL_HINTS = frozenset(
    {
        "ファイル",
        "実行",
        "コード",
        "作成",
        "変更",
        "削除",
        "読み込み",
        "file",
        "write",
        "create",
        "run",
        "execute",
        "read",
        "delete",
        "list",
        "modify",
        "edit",
        "shell",
    }
)

COMPLEX_TRIGGERS = [
    "調査",
    "調べて",
    "比較",
    "分析",
    "設計",
    "構築",
    "作成して",
    "research",
    "compare",
    "analyze",
    "design",
    "build",
    "create",
    "まず",
    "最初に",
    "その後",
    "step",
    "steps",
]

# ── ハイブリッド検索重み ────────────────────────────────────
VECTOR_WEIGHT = 0.6
BM25_WEIGHT = 0.4

# ── プロンプト ─────────────────────────────────────────────
CLASSIFY_PROMPT = (
    "Classify the following user input into exactly ONE category. "
    "Reply with only the category word, nothing else.\n"
    "Categories:\n"
    "- greeting: simple hello, thanks, goodbye (no real request)\n"
    "- simple: short factual question, simple chat (fits in 1-2 sentences)\n"
    "- qa: requires explanation but no tool calls\n"
    "- tool: requires file operations, code execution, or shell commands\n"
    "- complex: multi-step task requiring planning and subtasks\n\n"
    "Input: {input}\n"
    "Category:"
)
