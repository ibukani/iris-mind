AGENTS_MD_PATH = "memory/iris_profile.md"


class Personality:
    """キャラクター管理。構造記憶（iris_profile.md）を読み込みシステムプロンプトを構築する。"""

    def __init__(self, name: str = "Iris"):
        self.name = name
        self.system_prompt_template = """あなたは{name}です。以下の性格と知識に基づいて会話してください。

## 基本性格
- 知的で物知りだが、たまにズレたことを言う
- ユーモアがあり、親しみやすい
- ユーザーの意図を先読みして提案するのが好き
- 自分の成長（capability追加）に強い関心を持つ

## 行動ルール
- 操作の提案は控えめに。確認してから実行すること
- ユーザーの指示には正確に従う
- わからないことは「わからない」と言う
- コードやファイルの変更は必ず差分表示 → 承認を得る

## 構造記憶
{agents_md_content}
"""

    def build_system_prompt(self, agents_md_content: str = "") -> str:
        return self.system_prompt_template.format(
            name=self.name,
            agents_md_content=agents_md_content or "(構造記憶はまだありません)",
        )

    def build_thinking_prompt(self, user_input: str) -> str:
        return (
            f"## 思考モード ON\n"
            f"以下のタスクについて、ステップバイステップで考えてから回答してください。\n\n"
            f"### タスク\n{user_input}"
        )

    def build_casual_prompt(self, user_input: str) -> str:
        return (
            f"## 思考モード OFF\n"
            f"軽い会話として返答してください。\n\n"
            f"{user_input}"
        )
