import time

import grpc
import pytest

from iris.io.session.manager import SessionConfig, SessionManager
from iris.io.transport import grpc_service_pb2, grpc_service_pb2_grpc
from iris.io.transport.grpc_server import GrpcListener


def test_grpc_server_lifecycle():
    session_mgr = SessionManager(SessionConfig(access_token="test_secret"))
    listener = GrpcListener(session_mgr)

    # 起動
    listener.start("127.0.0.1", 19876)
    time.sleep(0.5)

    # 停止
    listener.stop()


def test_grpc_server_auth_and_communication():
    session_mgr = SessionManager(SessionConfig(access_token="test_secret"))

    received_messages = []
    received_commands = []

    def on_message(msg):
        received_messages.append(msg)

    def on_command(cmd):
        received_commands.append(cmd)

    listener = GrpcListener(session_mgr, on_message=on_message, on_command=on_command)
    listener.start("127.0.0.1", 19876)
    time.sleep(0.5)

    try:
        # 正しい認証トークンで接続
        metadata = [
            ("access_token", "test_secret"),
            ("role", "test_client"),
            ("permissions", "send_chat,receive_chat,send_command"),
        ]

        channel = grpc.insecure_channel("127.0.0.1:19876")
        stub = grpc_service_pb2_grpc.IrisServiceStub(channel)

        # 双方向ストリームの開始
        def request_generator():
            # 1. チャットメッセージ送信
            msg = grpc_service_pb2.Message(
                id="msg_1",
                direction="request",
                msg_type="chat",
                content="Hello World",
            )
            yield grpc_service_pb2.ClientFrame(message=msg)
            time.sleep(0.2)

            # 2. コマンド送信
            cmd = grpc_service_pb2.CommandInput(
                id="cmd_1",
                content="/status",
            )
            yield grpc_service_pb2.ClientFrame(command=cmd)
            time.sleep(0.2)

        _ = stub.BidirectionalStream(request_generator(), metadata=metadata)

        # サーバー側がキューイングで何かしら送り返してくるかをチェック
        # ここではメッセージ送信がコールバックされたことを確認
        time.sleep(0.5)

        assert len(received_messages) == 1
        assert received_messages[0].content == "Hello World"
        assert received_messages[0].source_role == "test_client"

        assert len(received_commands) == 1
        assert received_commands[0].content == "/status"

    finally:
        listener.stop()


def test_grpc_server_auth_failure():
    session_mgr = SessionManager(SessionConfig(access_token="test_secret"))
    listener = GrpcListener(session_mgr)
    listener.start("127.0.0.1", 19876)
    time.sleep(0.5)

    try:
        # 間違ったトークンで接続
        metadata = [
            ("access_token", "wrong_secret"),
            ("role", "test_client"),
        ]

        channel = grpc.insecure_channel("127.0.0.1:19876")
        stub = grpc_service_pb2_grpc.IrisServiceStub(channel)

        responses = stub.BidirectionalStream(iter([]), metadata=metadata)
        with pytest.raises(grpc.RpcError) as excinfo:
            list(responses)

        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED

    finally:
        listener.stop()
