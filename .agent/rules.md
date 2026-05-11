# Iris プロジェクトルール（コーディングエージェント向け）

## プロジェクト概要
Iris は自律的に行動・進化できるAIアシスタント。Python製でOllama上のQwen3.5 9Bをデフォルトモデルとする。

## 重要な用語の区別
- **Iris** → このプロジェクトで製作中のAI（作る対象）
- **コーディングエージェント** → プロジェクトを支援するAI（あなた = 現在の会話相手）

## ディレクトリ構成
- `core/` → エンジン本体（config, llm_bridge, personality, reflexion）
- `capabilities/` → 機能モジュール（file_ops, code_exec, self_mod など）
- `memory/` → 記憶管理（iris_profile.md, stores.py）
- `docs/` → 設計ドキュメント

## Iris の記憶体系
- `memory/iris_profile.md`: Irisの構造記憶（自己認識用、上限2KB固定）
- EpisodicStore + SemanticStore: JSONLベースの作業・意味記憶

## コーディング規約
- 変更差分はユーザーに提示→承認を得てから適用
- コード変更時の lint/typecheck は必須
- 新capabilityは `capabilities/<name>/server.py` に配置
- `__init__.py` を各パッケージに配置する

## 技術スタック
- Python 3.13+, ollama, pydantic, pyyaml, rich, prompt_toolkit
- OS: Windows 11, GPU: RTX 4070 SUPER (12GB VRAM)
