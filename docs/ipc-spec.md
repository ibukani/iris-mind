# Iris Mind 通信プロトコル仕様 v2.0 (gRPC 移行版)

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
接続開始時に送信される gRPC メタデータ（`access_token`, `role`, `permissions`）に基づいて認証が行われ、成功するとストリームが維持される。認証に失敗した場合は gRPC エラーコード（`UNAUTHENTICATED`）を返して即座に終了する。

### 2.3 Proto 定義 (`proto/iris/io/transport/grpc_service.proto`)

```protobuf
syntax = "proto3";

package iris.io.transport;

service IrisService {
  rpc BidirectionalStream (stream BidirectionalStreamRequest) returns (stream BidirectionalStreamResponse);
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

message BidirectionalStreamRequest {
  oneof frame {
    Message message = 1;
    CommandInput command = 2;
  }
}

message BidirectionalStreamResponse {
  oneof frame {
    Message message = 1;
    CommandOutput command = 2;
  }
}
```

---

## 3. プロトコル概要

| 通信方向 | 種別 | 説明 |
|---------|------|------|
| Client → Server | `BidirectionalStreamRequest.message` | テキスト入力、制御、アクション結果 |
| Client → Server | `BidirectionalStreamRequest.command` | システムコマンド（`CommandInput` fast-path） |
| Server → Client | `BidirectionalStreamResponse.message` | 応答、アクション要求、確認（`direction:stream`/`direction:response` で配送） |
| Server → Client | `BidirectionalStreamResponse.command` | コマンド応答（`CommandOutput` fast-path） |

---

## 4. データ型定義

### 4.1 Permission (メタデータで指定)

認証メタデータの `permissions` キーにコンマ区切りで指定する。

| 値 | 説明 |
|----|------|
| `send_chat` | テキスト入力を送信可能 |
| `receive_chat` | 応答を受信可能 |
| `send_command` | `/` コマンドを送信可能 |
| `receive_command` | コマンド結果を受信可能 |
| `receive_log` | ログ・デバッグ情報を受信可能 |
| `interrupt` | 生成中断を要求可能 |
| `execute_action` | アクション実行要求を受信可能 |

### 4.2 Direction (`Message.direction`)

| 値 | 方向 | 説明 |
|----|------|------|
| `request` | Client→Server | クライアントからのリクエスト |
| `response` | Server→Client | サーバーからの単一応答（最終結果） |
| `stream` | Server→Client | ストリーミング中継（`state` と併用） |
| `event` | Server→Client | イベント通知（ブロードキャスト等） |

### 4.3 msg_type 定義 (`Message.msg_type`)

| msg_type | 通信方向 | 説明 |
|----------|---------|------|
| `chat` | 双方向 | テキスト会話メッセージ（`direction:stream` でストリーミング、`direction:response` で最終応答） |
| `system` | Client→Server | システム制御メッセージ |
| `interrupt` | Client→Server | 生成中断要求 |
| `execute` | Server→Client | アクション実行要求（tools使用時） |
| `execute_result` | Client→Server | アクション実行結果 |
| `ack` | Server→Client | 受信確認（`metadata.ack_required` 時） |
| `error` | Server→Client | エラー通知 |

---

## 5. 接続シーケンス

### 5.1 通常フロー

```mermaid
sequenceDiagram
    participant Client
    participant Server as GrpcServer
    participant Kernel as Iris Kernel

    Client->>Server: BidirectionalStream (metadata: access_token, role, permissions)
    activate Server
    Note over Server: メタデータ検証・セッション生成
    Server-->>Client: 接続確立 (双方向ストリーム開始)

    Client->>Server: BidirectionalStreamRequest(Message: msg_type="chat", direction="request", content="Hello")
    Server->>Kernel: MessageEvent
    activate Kernel
    Kernel-->>Server: OutputRequest(thinking)
    Server-->>Client: BidirectionalStreamResponse(Message: msg_type="chat", direction="stream", state="thinking")
    Kernel-->>Server: OutputRequest(speaking, content="Hello")
    Server-->>Client: BidirectionalStreamResponse(Message: msg_type="chat", direction="stream", state="speaking", content="Hello!")
    Kernel-->>Server: OutputRequest(done)
    Server-->>Client: BidirectionalStreamResponse(Message: msg_type="chat", direction="stream", state="done")
    Kernel-->>Server: OutputRequest(response)
    Server-->>Client: BidirectionalStreamResponse(Message: msg_type="chat", direction="response", content="Hello! How can I help you today?")
    deactivate Kernel
    deactivate Server
```

### 5.2 コマンドフロー (Fast-Path)

```mermaid
sequenceDiagram
    participant Client
    participant Server as GrpcServer
    participant Kernel as Iris Kernel

    Client->>Server: BidirectionalStreamRequest(CommandInput: content="/status")
    activate Server
    Server->>Kernel: Handle Command
    Note over Kernel: CommandHandler で直接処理
    Kernel-->>Server: CommandResult
    Server-->>Client: BidirectionalStreamResponse(CommandOutput: content="Status: OK")
    deactivate Server
```

---

## 6. 実装例

### 6.1 Python クライアント例

```python
import grpc
from iris.io.transport import grpc_service_pb2 as pb2
from iris.io.transport import grpc_service_pb2_grpc as pb2_grpc


def generate_messages(session_id: str):
    yield pb2.BidirectionalStreamRequest(
        message=pb2.Message(
            id="msg_001",
            msg_type="chat",
            session_id=session_id,
            direction="request",
            content="Hello Iris!",
        )
    )


def run():
    metadata = [
        ("access_token", "your_access_token"),
        ("role", "cli"),
        ("permissions", "send_chat,receive_chat,send_command,receive_command"),
    ]

    with grpc.insecure_channel("localhost:9876") as channel:
        stub = pb2_grpc.IrisServiceStub(channel)
        responses = stub.BidirectionalStream(
            generate_messages(""), metadata=metadata
        )

        for response in responses:
            if response.HasField("message"):
                msg = response.message
                if msg.direction == "stream":
                    print(f"[{msg.state}] {msg.content}")
                elif msg.direction == "response":
                    print(f"Final Response: {msg.content}")
            elif response.HasField("command"):
                print(f"Command Result: {response.command.content}")


if __name__ == "__main__":
    run()
```

### 6.2 Rust クライアント例 (tonic)

```rust
use iris::io::transport::iris_service_client::IrisServiceClient;
use iris::io::transport::{
    bidirectional_stream_request, bidirectional_stream_response, Message,
};
use tonic::metadata::MetadataValue;
use tonic::Request;

pub mod iris {
    pub mod io {
        pub mod transport {
            tonic::include_proto!("iris.io.transport");
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let channel = tonic::transport::Channel::from_static("http://127.0.0.1:9876")
        .connect()
        .await?;

    let token: MetadataValue<_> = "your_access_token".parse()?;
    let role: MetadataValue<_> = "cli".parse()?;
    let permissions: MetadataValue<_> =
        "send_chat,receive_chat,send_command,receive_command".parse()?;

    let mut client = IrisServiceClient::with_interceptor(channel, move |mut req: Request<()>| {
        req.metadata_mut().insert("access_token", token.clone());
        req.metadata_mut().insert("role", role.clone());
        req.metadata_mut().insert("permissions", permissions.clone());
        Ok(req)
    });

    let outbound = tokio_stream::iter(vec![
        iris::io::transport::BidirectionalStreamRequest {
            frame: Some(bidirectional_stream_request::Frame::Message(Message {
                id: "msg_001".to_string(),
                msg_type: "chat".to_string(),
                session_id: "".to_string(),
                direction: "request".to_string(),
                source_role: "cli".to_string(),
                target_role: "mind".to_string(),
                content: "Hello Iris!".to_string(),
                ..Default::default()
            })),
        },
    ]);

    let response = client.bidirectional_stream(outbound).await?;
    let mut inbound = response.into_inner();

    while let Some(frame) = inbound.message().await? {
        if let Some(f) = frame.frame {
            match f {
                bidirectional_stream_response::Frame::Message(msg) => {
                    println!("Received message: {}", msg.content);
                }
                bidirectional_stream_response::Frame::Command(cmd) => {
                    println!("Received command output: {}", cmd.content);
                }
            }
        }
    }

    Ok(())
}
```

---

## 7. エラーハンドリング

| 状況 | 動作 / エラーコード |
|------|------|
| 認証失敗 | gRPC ステータスコード `UNAUTHENTICATED` (16) を返して接続切断 |
| 不正なリクエスト引数 | gRPC ステータスコード `INVALID_ARGUMENT` (3) |
| 内部エラー | gRPC ステータスコード `INTERNAL` (13) |
| 権限不足 | BidirectionalStreamResponse 内で `error` メッセージを送信、または `PERMISSION_DENIED` (7) |
| 接続断 | サーバーは当該セッション情報を削除 |
