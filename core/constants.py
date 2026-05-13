"""共通定数・設定値。"""

from enum import Enum


class Complexity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── モデル関連 ──────────────────────────────────────────────
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_GPU = 0

# ── 複雑性判定閾値 ─────────────────────────────────────────
COMPLEXITY_LOW_THRESHOLD = 2
COMPLEXITY_HIGH_THRESHOLD = 4

# ── 応答トークン上限 ─────────────────────────────────────
SHORT_GREET_TOKENS = 64

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
