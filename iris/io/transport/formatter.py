from __future__ import annotations

from typing import Any

from iris.io.models import Identity

from . import grpc_service_pb2 as _pb2


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
    msg = _pb2.Message(  # type: ignore[attr-defined]
        id=data.get("id", ""),
        correlation_id=data.get("correlation_id", ""),
        session_id=data.get("session_id", ""),
        source_role=data.get("source_role", ""),
        target_role=data.get("target_role", ""),
        direction=data.get("direction", ""),
        msg_type=data.get("msg_type", ""),
        content=data.get("content", ""),
        content_type=data.get("content_type", ""),
        state=data.get("state") or "",
    )
    meta = data.get("metadata", {})
    uid = data.get("account_id", "")
    if uid:
        meta["account_id"] = uid
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
