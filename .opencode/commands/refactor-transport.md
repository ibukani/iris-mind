---
description: io/transport レイヤーの責務整理を段階的に行う。まず計画だけを作る。
---

@planner

対象: `iris/io/transport`

まずコード変更せず、以下の観点で計画を作ってください。

## 目的

gRPC server を薄くし、通信境界・protobuf変換・認可・エラー変換を分離する。

## 見るファイル

```text
iris/io/transport/grpc_server.py
iris/io/transport/
proto/
```

## 計画に含めること

- grpc_server.py から切り出すべき責務
- grpc_lifecycle.py が必要か
- grpc_auth.py が必要か
- grpc_session_adapter.py が必要か
- grpc_event_adapter.py が必要か
- grpc_error_mapping.py が必要か
- proto schema を変更する必要があるか
- generated file に触る必要があるか
- 追加・更新すべきテスト

## 注意

- proto schema は必要がなければ変更しない
- generated file は手編集しない
- protobuf 依存を domain layer に漏らさない
- 実装はまだ行わないでください。計画が合意されたら `/implement-plan` を使います。
