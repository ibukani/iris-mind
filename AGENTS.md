# Iris 構造記憶

## Repository Structure
- core/ → エンジン本体
- capabilities/ → MCPサーバ郡
- memory/ → 記憶管理

## Available Capabilities
- read_file: ファイル読み込み
- write_file: ファイル書き込み
- list_files: ディレクトリ一覧

## Conventions
- 新capabilityは capabilities/<name>/server.py に配置
- ユーザーに操作を提案する前に必ず確認を取る
- コード変更時は必ず差分表示 → 承認を得る
