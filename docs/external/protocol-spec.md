# Iris Mind 通信プロトコル仕様 v2.0 (gRPC 移行版)

> **ドキュメント構成**: 本仕様は以下の3文書で構成される。
> - **本ファイル** — 概要・通信方式・プロトコル概要・エラーハンドリング
> - [`protocol-types.md`](./protocol-types.md) — データ型定義（Permission, Direction, Message, Identity, ControlMessage）
> - [`protocol-flows.md`](./protocol-flows.md) — 接続シーケンス図・実装例

## 1. 概要

Iris Mind は gRPC を介して外部プロセスと通信する。本ドキュメントは言語非依存のプロトコル仕様を定義する。

### 設計原則

- **スキーマ定義の明確化**: Protocol Buffers (proto3) による明示的な型定義
- **双方向ストリーミング**: 単一の持続的コネクション上での非同期双方向通信
- **メタデータ認証**: gRPC メタデータによるセキュリティとセッション初期化の統合
- **Role/Permission 分離**: 権限モデルを `role`（識別子）と `permissions`（権限セット）に分離

---

## 2. 通信方式

### 2.1 トランスポート

**gRPC over HTTP/2**

- ポート: `9876`（デフォルト）
- 同一マシン内プロセス間通信専用（デフォルト）
- 設定によりリモート接続可能（メタデータ内の `access_token` 必須）

### 2.2 セッション構成

1セッション = 1つの双方向ストリーミング RPC (`IrisService.BidirectionalStream`)。
接続開始時に送信される gRPC メタデータ（`access_token`, `role`, `permissions`, `session_tag`, `description`）に基づいて認証が行われ、成功するとストリームが維持される。認証に失敗した場合は gRPC エラーコード（`UNAUTHENTICATED`）を返して即座に終了する。

**Session ID の扱い**:
- セッションID はサーバーが認証時に採番（16文字ランダム）し、ストリームに暗黙的に紐づく
- クライアントは `Message.session_id` / `CommandInput.session_id` を**空文字のまま送信してよい**。サーバーは自ストリームのセッションID で上書きする
- サーバーが送信する `Message.session_id` には常に正しいセッションID が格納される。クライアントは必要に応じて最初のメッセージから取得・保持する

**グループチャット識別**: 単一接続で複数ユーザーを扱う場合、各メッセージの `speaker` に発話者Identityを、`room_id` に会話ルームIDを設定する。Iris は `speaker` からAccountを自動解決し、応答にも同じ `room_id` を伝搬する。

> **room_id の形式**: `room_id` は `room.create` が返す `uuid4().hex[:16]` 形式の16進文字列（例: `"a1b2c3d4e5f6g78"`）である。`"discord:guild_1:channel_1"` のような colon 区切り文字列はクライアント側のルーティングラベルであり、room_id の値としては使用しない。クライアントは外部識別子と UUID room_id のマッピングを自身で管理する。

### 2.3 Proto 定義 (`proto/iris/io/transport/grpc_service.proto`)

```protobuf
syntax = "proto3";

package iris.io.transport;

enum Permission {
  PERMISSION_UNSPECIFIED = 0;
  PERMISSION_SEND_CHAT = 1;
  PERMISSION_RECEIVE_CHAT = 2;
  PERMISSION_SEND_COMMAND = 3;
  PERMISSION_RECEIVE_COMMAND = 4;
  PERMISSION_RECEIVE_LOG = 5;
  PERMISSION_INTERRUPT = 6;
  PERMISSION_EXECUTE_ACTION = 7;
  PERMISSION_SEND_VOICE_INDICATOR = 8;
}

message Identity {
  string provider = 1;
  string subject = 2;
  string provider_name = 3;
  map<string, string> metadata = 4;
}

message Message {
  string id = 1;
  string correlation_id = 2;
  string session_id = 3;
  string source_role = 4;
  string target_role = 5;
  string direction = 6;
  string msg_type = 7;
  string content = 8;
  string content_type = 9;
  string state = 10;
  map<string, string> metadata = 11;
  Identity speaker = 12;
  string room_id = 13;
}

message CommandInput {
  string msg_type = 1;
  string id = 2;
  string session_id = 3;
  string source_role = 4;
  string content = 5;
}

message CommandOutput {
  string id = 1;
  string correlation_id = 2;
  string session_id = 3;
  string msg_type = 4;
  string content = 5;
  string state = 6;
}

message ControlMessage {
  string action = 1;
  string display_name = 2;
  string text = 3;
  string account_id = 4;
  Identity identity = 5;
  map<string, string> profile = 6;
  string room_id = 7;
  map<string, string> metadata = 8;
}

message BidirectionalStreamRequest {
  oneof frame {
    Message message = 1;
    CommandInput command = 2;
    ControlMessage control = 3;
  }
}

message BidirectionalStreamResponse {
  oneof frame {
    Message message = 1;
    CommandOutput command = 2;
    ControlMessage control = 3;
  }
}

service IrisService {
  rpc BidirectionalStream (stream BidirectionalStreamRequest) returns (stream BidirectionalStreamResponse);
}
```

---

## 3. プロトコル概要

| 通信方向 | 種別 | 説明 |
|---------|------|------|
| Client → Server | `BidirectionalStreamRequest.message` | テキスト入力、制御、アクション結果 |
| Client → Server | `BidirectionalStreamRequest.message` (msg_type=voice_indicator) | 音声録音状態の制御信号（sensory/pending_input非保存、EventBus経由でProactive抑制） |
| Client → Server | `BidirectionalStreamRequest.command` | システムコマンド（`CommandInput` fast-path） |
| Client → Server | `BidirectionalStreamRequest.control` | アカウント制御プロトコル |
| Server → Client | `BidirectionalStreamResponse.message` | 応答、アクション要求、確認（`direction:stream`/`direction:response` で配送） |
| Server → Client | `BidirectionalStreamResponse.command` | コマンド応答（`CommandOutput` fast-path） |
| Server → Client | `BidirectionalStreamResponse.control` | アカウント制御応答・presence通知 |

**備考:**
- `execute` / `execute_result`: 現在サーバーサイドで全ツール実行が完結。クライアントへの実行委譲は未実装。権限・msg_type は将来拡張用に確保。
- `interrupt`: クライアント→サーバーの `msg_type=interrupt` 送信による生成キャンセルは現在非対応。内部割込み（新規入力到着時）のみ動作。

---

## 4. エラーハンドリング

| 状況 | 動作 / エラーコード |
|------|------|
| 認証失敗 | gRPC ステータスコード `UNAUTHENTICATED` (16) を返して接続切断 |
| 不正なリクエスト引数 | gRPC ステータスコード `INVALID_ARGUMENT` (3) |
| 内部エラー | gRPC ステータスコード `INTERNAL` (13) |
| 権限不足 | BidirectionalStreamResponse 内で `error` メッセージを送信、または `PERMISSION_DENIED` (7) |
| 接続断 | サーバーは当該セッション情報を削除。セッションを含む全ルームメンバーからセッションIDを除去し、セッションIDが空になったメンバーは自動退室。各ルームに `presence.left` を自動発行、自発発話の抑制を解除する |
| direction が `request` 以外 | サーバーは `Message(msg_type="response", content="unexpected direction from client: {direction}. use 'request'")` を返す |
| speaker 未設定 | サーバーは `Message(msg_type="response", content="speaker is required for inbound messages")` を返す |
| chat メッセージで content が空 | サーバーは `Message(msg_type="response", content="content is required for chat messages")` を返す |
| room_id が空 | サーバーは `Message(msg_type="response", content="room_id is required")` を返す |
| 存在しない room_id | サーバーは `Message(msg_type="response", content="room not found: {room_id}")` を返す |

**補足:**
- `msg_type=error` は permission マップに定義されているが、現在サーバーはこの型を生成しない。
- エラーは `msg_type="response"` の `content` にエラーメッセージを含み、`metadata` に `"error": "true"` が設定される。クライアントは `msg.metadata.get("error") == "true"` で機械的にエラーを判別できる。
- `target_role` が `"mind"` 以外の場合、メッセージはセッション間ルーティングに回り、Iris は処理しない。該当する宛先セッションがない場合は応答が返らないため注意が必要（protocol-flows.md §1.3 参照）。
