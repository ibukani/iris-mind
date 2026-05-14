# ADR-001: 3-Process Decomposition (Input / Kernel / Output)

- **Status**: Accepted
- **Date**: 2026-05-14
- **Author**: コーディングエージェント + 人間の協働

## Context

Iris v0.2 は単一プロセス・単一スレッド（タイマースレッド除く）で動作している。
このアーキテクチャには以下の限界がある：

1. **複数入力の同時受付不可**: `input()` のブロッキングループが1つしか持てない。
   将来的に CLI + WebSocket + Discord Bot 等の複数入力を同時に受け付けることが不可能。
2. **出力処理の干渉**: 応答生成中に出力（表示）がブロックされる可能性がある。
3. **障害分離の欠如**: 入力処理のバグが Kernel 全体をダウンさせる。
4. **UI 差し替えのリスク**: GUI や音声出力に切り替える際、同じプロセス内での移行はリスクが高い。

### 五大装置アナロジー

PC の五大装置（入力・出力・記憶・演算・制御）に着想を得て、
Iris を以下の3プロセスに分解する：

| プロセス | 五大装置相当 | 責務 |
|----------|-------------|------|
| Input Process | 入力装置 | キーボード入力受付、音声認識、API受付 |
| Kernel Process | 制御・演算・記憶 | 状態管理、会話処理、LLM呼び出し、記憶管理 |
| Output Process | 出力装置 | 画面表示、音声合成、API応答 |

PC の周辺機器が別電源で動作するように、各プロセスは独立して起動・停止・置換可能とする。

## Decision

### 1. IPC 方式: Windows Named Pipes

`multiprocessing.connection.Listener` / `Client` の `AF_PIPE` を使用する。

**選定理由**:
- Windows 環境専用（クロスプラットフォームは将来の課題）
- カーネルモード動作で TCP より低レイテンシ
- Python 標準ライブラリのみで実装可能（追加依存なし）
- シリアライズに pickle を利用可能（`multiprocessing.connection` の標準動作）
- 将来 TCP に変更する場合も `family="AF_INET"` に変えるだけ

### 2. Proactive 応答追跡の Kernel 側移動

従来 CLIAdapter（Input 側）にあった `_check_proactive_response()` を
Kernel Process 内の `ProactiveResponseTracker` として再実装する。

**理由**:
- Input Process を純粋な「入力転送」に保つ（stateless）
- 複数 Input 接続時に応答評価が正しく動作する
- 状態が Kernel 内で完結 → デバッグ容易

### 4. イベント設計

全イベントに `trace_id`（UUID4）を追加し、3プロセス横断で追跡可能にする。

```python
@dataclass
class Event:
    timestamp: datetime
    source: str
    trace_id: str  # ← 新規追加
```

### 5. デバッグ戦略

| 課題 | 対策 |
|------|------|
| 非決定性 (タイミングバグ) | ReplayableTransport でイベント列を記録・再生 |
| 部分障害 | Controller がヘルスチェック + 自動再起動 |
| 因果関係追跡 | trace_id によるログ横断検索 |
| テスト | FakeEventBus (in-memory Protocol) でプロセス不要の単体テスト |

## Consequences

### 良い影響

- 複数入力ソースの同時接続が可能に
- 障害分離（Output が死んでも Kernel は継続動作）
- UI 差し替えが容易（Output Process だけ差し替え）
- 開発の並列化（Input / Kernel / Output を独立して開発）

### 悪影響・リスク

- デバッグ複雑性の増加（プロセス間跨ぎの追跡が必要）
- IPC オーバーヘッド（シリアライズ + 転送）
- 起動・停止シーケンスの複雑化（3プロセスのライフサイクル管理）
- 状態の一貫性確保（Kernel クラッシュ時の復旧設計）

## Compliance

- ADR は `docs/adr/` に保存する
- 設計判断の変更時は新規 ADR を作成し、本 ADR を Superseded とする
- コード変更と ADR 更新は同一コミットに含める
