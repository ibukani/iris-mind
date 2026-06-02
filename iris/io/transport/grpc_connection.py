"""gRPC 接続 (GrpcConnection) と proto repeated フィールドへの書き込みヘルパ。

GrpcServer 内部でだけ利用する。`send_bytes` は別スレッド (SessionManager router)
からも安全に渡せるよう、event loop に `call_soon_threadsafe` でキューイングする。
"""

from __future__ import annotations

import asyncio
from typing import Any


class GrpcConnection:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.loop = loop

    def send_bytes(self, raw: bytes) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, raw)

    def close(self) -> None:
        pass


def set_proto_from_dict(proto_repeated: Any, value: Any, builder: Any) -> None:
    """proto の repeated フィールドに dict 値を書き込む。

    - builder が dict を返す: 内部でキー/値を 1 つずつ書き込む
    - builder が proto を返す: CopyFrom で置き換える
    """
    if isinstance(value, dict):
        result = builder(value)
        if isinstance(result, dict):
            for k, v in result.items():
                proto_repeated[str(k)] = str(v)
        else:
            proto_repeated.CopyFrom(result)


__all__ = ["GrpcConnection", "set_proto_from_dict"]
