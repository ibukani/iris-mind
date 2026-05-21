"""
Iris Kernel Debug CLI — gRPC接続による状態診断・トレース取得

使い方:
    python -m debug_tools.cli state [<path>] [--history] [--json] [--spawn]
    python -m debug_tools.cli events [n] [--type=TYPE] [--spawn]
    python -m debug_tools.cli health [--spawn]
    python -m debug_tools.cli report [--spawn]

--spawn: Irisが未起動の場合、自動で起動する（要: python main.py）

環境変数:
    IRIS_HOST        (default: 127.0.0.1)
    IRIS_PORT        (default: 9876)
    IRIS_ACCESS_TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time

import grpc

from iris.io.transport import grpc_service_pb2 as pb2
from iris.io.transport import grpc_service_pb2_grpc as pb2_grpc

SPAWN_TIMEOUT = 30


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iris-debug", description="Iris Kernel Debug CLI")
    parser.add_argument("--spawn", action="store_true", help="Auto-start Iris if not running")
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


def _build_metadata(args: argparse.Namespace) -> list[tuple[str, str]]:
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


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (TimeoutError, OSError):
        return False


def _spawn_iris(host: str, port: int, timeout: int = SPAWN_TIMEOUT) -> subprocess.Popen | None:
    """Iris をサブプロセスとして起動し、ポートが開くのを待つ。"""
    print(f"Iris not running on {host}:{port}. Starting...", file=sys.stderr)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(root, "main.py")
    if not os.path.isfile(main_py):
        print(f"Error: {main_py} not found", file=sys.stderr)
        return None
    proc = subprocess.Popen(
        [sys.executable, main_py],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(host, port):
            print("Iris is ready.", file=sys.stderr)
            return proc
        if proc.poll() is not None:
            print(f"Iris process exited unexpectedly (code={proc.returncode})", file=sys.stderr)
            return None
        time.sleep(0.5)
    print(f"Timeout: Iris did not start within {timeout}s", file=sys.stderr)
    proc.kill()
    return None


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
        if field == "message":
            continue
        if field == "command":
            result += resp.command.content
    return result.strip()


def main() -> None:
    args = _parse_args()
    host = os.environ.get("IRIS_HOST", "127.0.0.1")
    port = int(os.environ.get("IRIS_PORT", "9876"))
    target = f"{host}:{port}"
    metadata = _build_metadata(args)
    spawned_proc: subprocess.Popen | None = None

    if not _port_open(host, port):
        if args.spawn:
            spawned_proc = _spawn_iris(host, port)
            if spawned_proc is None:
                sys.exit(1)
        else:
            print(f"Error: Cannot connect to {target}\n  Use --spawn to auto-start Iris", file=sys.stderr)
            sys.exit(1)

    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
    except Exception:
        print(f"Error: gRPC connection to {target} failed", file=sys.stderr)
        if spawned_proc:
            spawned_proc.kill()
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
        if spawned_proc:
            spawned_proc.kill()
        sys.exit(1)

    if args.json and args.command == "state":
        try:
            parsed = json.loads(output)
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
            return
        except json.JSONDecodeError:
            pass

    print(output)


if __name__ == "__main__":
    main()
