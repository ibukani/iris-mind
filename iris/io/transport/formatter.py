from __future__ import annotations

from typing import Any

from iris.io.models import Identity

from . import grpc_service_pb2 as _pb2

_DIRECTION_MAP: dict[str, int] = {
    "request": _pb2.DIRECTION_REQUEST,  # type: ignore[attr-defined]
    "response": _pb2.DIRECTION_RESPONSE,  # type: ignore[attr-defined]
    "stream": _pb2.DIRECTION_STREAM,  # type: ignore[attr-defined]
    "event": _pb2.DIRECTION_EVENT,  # type: ignore[attr-defined]
}

_STREAM_STATE_MAP: dict[str, int] = {
    "thinking": _pb2.STREAM_STATE_THINKING,  # type: ignore[attr-defined]
    "speaking": _pb2.STREAM_STATE_SPEAKING,  # type: ignore[attr-defined]
    "done": _pb2.STREAM_STATE_DONE,  # type: ignore[attr-defined]
    "interrupted": _pb2.STREAM_STATE_INTERRUPTED,  # type: ignore[attr-defined]
}

_REVERSE_DIRECTION: dict[int, str] = {v: k for k, v in _DIRECTION_MAP.items()}
_REVERSE_STREAM_STATE: dict[int, str] = {v: k for k, v in _STREAM_STATE_MAP.items()}


def parse_direction(proto_value: int) -> str:
    return _REVERSE_DIRECTION.get(proto_value, "")


def parse_stream_state(proto_value: int) -> str | None:
    return _REVERSE_STREAM_STATE.get(proto_value)


def build_command_frame(data: dict[str, Any]) -> Any:
    return _pb2.CommandOutput(  # type: ignore[attr-defined]
        id=data.get("id", ""),
        correlation_id=data.get("correlation_id", ""),
        session_id=data.get("session_id", ""),
        msg_type=data.get("msg_type", ""),
        content=data.get("content", ""),
        state=data.get("state") or "",
    )


def build_message_frame(data: dict[str, Any]) -> Any:
    direction_raw = data.get("direction", "")
    state_raw = data.get("state") or ""

    msg = _pb2.Message(  # type: ignore[attr-defined]
        id=data.get("id", ""),
        correlation_id=data.get("correlation_id", ""),
        session_id=data.get("session_id", ""),
        source_role=data.get("source_role", ""),
        target_role=data.get("target_role", ""),
        direction=_DIRECTION_MAP.get(direction_raw, _pb2.DIRECTION_UNSPECIFIED),  # type: ignore[attr-defined]
        msg_type=data.get("msg_type", ""),
        content=data.get("content", ""),
        content_type=data.get("content_type", ""),
        state=_STREAM_STATE_MAP.get(state_raw, _pb2.STREAM_STATE_UNSPECIFIED),  # type: ignore[attr-defined]
        account_id=data.get("account_id", ""),
    )
    meta = data.get("metadata", {})
    room_id = data.get("room_id", "")
    if room_id:
        msg.room_id = room_id
    for k, v in meta.items():
        msg.metadata[k] = str(v)
    speaker = data.get("speaker")
    if isinstance(speaker, dict):
        msg.speaker.CopyFrom(build_identity_frame(speaker))
    return msg


def build_identity_frame(data: dict[str, Any]) -> Any:
    identity = _pb2.Identity(  # type: ignore[attr-defined]
        provider=str(data.get("provider", "")),
        subject=str(data.get("subject", "")),
        provider_name=str(data.get("provider_name", "")),
    )
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        for k, v in metadata.items():
            identity.metadata[str(k)] = str(v)
    return identity


def parse_message_metadata(metadata_proto: Any) -> dict[str, Any]:
    metadata = {}
    for k, v in metadata_proto.items():
        if v.lower() == "true":
            metadata[k] = True
        elif v.lower() == "false":
            metadata[k] = False
        else:
            metadata[k] = v
    return metadata


def parse_identity(identity_proto: Any) -> Identity | None:
    if not identity_proto.provider and not identity_proto.subject:
        return None
    return Identity(
        provider=identity_proto.provider,
        subject=identity_proto.subject,
        provider_name=identity_proto.provider_name,
        metadata=dict(identity_proto.metadata),
    )
