"""
Iris Kernel Debug CLI — gRPC接続による状態診断・トレース取得

使い方:
    python -m debug_tools.cli state [<path>] [--history] [--json] [--spawn]
    python -m debug_tools.cli events [n] [--type=TYPE] [--spawn]
    python -m debug_tools.cli health [--spawn]
    python -m debug_tools.cli report [--spawn]

--spawn: Irisが未起動の場合、自動で起動する（要: python main.py）
         デフォルトで終了時にIrisをシャットダウンする。
--keep-alive: --spawn と併用、Irisを生かしたまま抜ける。

環境変数:
    IRIS_HOST        (default: 127.0.0.1)
    IRIS_PORT        (default: 9876)
    IRIS_ACCESS_TOKEN
"""

from __future__ import annotations

import argparse
import atexit
import os
import socket
import subprocess
import sys
import time

import grpc
import orjson

from iris.io.transport import grpc_service_pb2 as pb2
from iris.io.transport import grpc_service_pb2_grpc as pb2_grpc

SPAWN_TIMEOUT = 30
_spawned_proc: subprocess.Popen | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iris-debug", description="Iris Kernel Debug CLI")
    parser.add_argument("--spawn", action="store_true", help="Auto-start Iris if not running")
    parser.add_argument("--keep-alive", action="store_true", help="Keep Iris running after command")
    parser.add_argument("--debug-mode", action="store_true", help="Start Iris in --debug mode (skip LLM/ChromaDB)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_state = sub.add_parser("state", help="Show system state (dot-path supported)")
    p_state.add_argument("path", nargs="?", default="", help="Dot-path like limbic.emotion")
    p_state.add_argument("--history", action="store_true", help="Show state change history")
    p_state.add_argument("--json", action="store_true", help="JSON output")
    p_state.add_argument("--n", type=int, default=10, help="History entry count")

    p_events = sub.add_parser("events", help="Show recent events")
    p_events.add_argument("n", nargs="?", type=int, default=10, help="Number of events")
    p_events.add_argument("--type", dest="type_filter", default="", help="Filter by event type")

    sub.add_parser("health", help="Health check all components")
    sub.add_parser("report", help="Generate Markdown debug report")

    return parser.parse_args()


def _build_metadata() -> list[tuple[str, str]]:
    token = os.environ.get("IRIS_ACCESS_TOKEN", "")
    meta = [
        ("access_token", token),
        ("role", "debug_cli"),
        ("identity", "debug-cli"),
    ]
    permissions = [
        "PERMISSION_SEND_COMMAND",
        "PERMISSION_RECEIVE_COMMAND",
    ]
    meta.append(("permissions", ",".join(permissions)))
    return meta


def _wait_port(host: str, port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except TimeoutError:
            continue
        except OSError:
            continue
    return False


def _spawn_iris(host: str, port: int, debug_mode: bool, timeout: int = SPAWN_TIMEOUT) -> subprocess.Popen | None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(root, "main.py")
    if not os.path.isfile(main_py):
        print(f"Error: {main_py} not found", file=sys.stderr)
        return None

    cmd = [sys.executable, main_py]
    if debug_mode:
        cmd.append("--debug")
    proc = subprocess.Popen(
        cmd,
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    global _spawned_proc
    _spawned_proc = proc

    if not _wait_port(host, port, timeout):
        print(f"Timeout: Iris did not start within {timeout}s", file=sys.stderr)
        proc.kill()
        proc.wait(timeout=5)
        return None
    return proc


def _shutdown_via_grpc(metadata: list) -> None:
    if _spawned_proc is None:
        return
    host = os.environ.get("IRIS_HOST", "127.0.0.1")
    port = int(os.environ.get("IRIS_PORT", "9876"))
    if not _wait_port(host, port, 3):
        return
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=3)
        stub = pb2_grpc.IrisServiceStub(channel)
        cmd = pb2.CommandInput(  # type: ignore[attr-defined]
            msg_type="command",
            id="shutdown-1",
            session_id="debug-cli",
            source_role="debug_cli",
            content="/shutdown",
        )
        req = pb2.BidirectionalStreamRequest(command=cmd)  # type: ignore[attr-defined]
        list(stub.BidirectionalStream(iter([req]), metadata=metadata, timeout=5))
    except Exception:  # noqa: S110
        pass


def _cleanup() -> None:
    global _spawned_proc
    if _spawned_proc is None:
        return
    if _spawned_proc.poll() is not None:
        _spawned_proc = None
        return
    try:
        _spawned_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _spawned_proc.kill()
        _spawned_proc.wait(timeout=5)
    _spawned_proc = None


def _run_command(stub: pb2_grpc.IrisServiceStub, command: str, metadata: list, timeout: int = 10) -> str:
    cmd = pb2.CommandInput(  # type: ignore[attr-defined]
        msg_type="command",
        id="debug-1",
        session_id="debug-cli",
        source_role="debug_cli",
        content=f"/{command}",
    )
    req = pb2.BidirectionalStreamRequest(command=cmd)  # type: ignore[attr-defined]
    responses = stub.BidirectionalStream(
        iter([req]),
        metadata=metadata,
        timeout=timeout,
    )
    result = ""
    for resp in responses:
        field = resp.WhichOneof("frame")
        if field == "command":
            result += resp.command.content
    return result.strip()


def main() -> None:
    global _spawned_proc
    args = _parse_args()
    host = os.environ.get("IRIS_HOST", "127.0.0.1")
    port = int(os.environ.get("IRIS_PORT", "9876"))
    metadata = _build_metadata()

    if not _wait_port(host, port, 2):
        if args.spawn:
            spawned = _spawn_iris(host, port, args.debug_mode)
            if spawned is None:
                sys.exit(1)
        else:
            print(f"Error: Cannot connect to {host}:{port}\n  Use --spawn to auto-start Iris", file=sys.stderr)
            sys.exit(1)

    atexit.register(_cleanup)

    channel = grpc.insecure_channel(f"{host}:{port}")
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
    except Exception:
        print(f"Error: gRPC connection to {host}:{port} failed", file=sys.stderr)
        _cleanup()
        sys.exit(1)

    stub = pb2_grpc.IrisServiceStub(channel)

    if args.command == "state":
        parts = [args.path] if args.path else []
        if args.history:
            parts.append("--history")
        if args.json:
            parts.append("--json")
        parts.append(f"--n={args.n}")
        cmd = "debug " + " ".join(parts) if parts else "debug state"
    elif args.command == "events":
        cmd = f"debug events --n={args.n}"
        if args.type_filter:
            cmd += f" --type={args.type_filter}"
    elif args.command == "health":
        cmd = "debug health"
    elif args.command == "report":
        cmd = "debug report"
    else:
        cmd = "debug help"

    try:
        output = _run_command(stub, cmd, metadata)
    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} {e.details()}", file=sys.stderr)
        _cleanup()
        sys.exit(1)
    except KeyboardInterrupt:
        _shutdown_via_grpc(metadata)
        _cleanup()
        sys.exit(130)

    if args.json and args.command == "state":
        try:
            parsed = orjson.loads(output.encode("utf-8"))
            print(orjson.dumps(parsed, option=orjson.OPT_INDENT_2).decode("utf-8"))
            return
        except orjson.JSONDecodeError:
            pass

    print(output)

    if _spawned_proc is not None and not args.keep_alive:
        print("Shutting down Iris...", file=sys.stderr)
        _shutdown_via_grpc(metadata)
        _cleanup()
        print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
