from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass


@dataclass
class _StateArgs:
    path: str
    history: bool = False
    as_json: bool = False
    n: int = 10


def _format_value(v: object, indent: int = 0) -> str:
    prefix = "  " * indent
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = []
        for k, val in v.items():
            lines.append(f"{prefix}{k}: {_format_value(val, indent + 1)}")
        return "\n".join(lines)
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(isinstance(x, str) for x in v):
            return ", ".join(str(x) for x in v)
        return "\n" + "\n".join(f"{prefix}- {_format_value(x)}" for x in v)
    return str(v)


def _format_state(state: object, path: str = "") -> str:
    if path:
        return _format_value(state)
    if isinstance(state, dict):
        lines = []
        for k, v in state.items():
            lines.append(f"{k}: {_format_value(v, 1)}")
        return "\n".join(lines)
    return str(state)


def _parse_state_args(args: str) -> _StateArgs:
    parts = args.strip().split()
    path = ""
    history = False
    as_json = False
    n = 10
    for p in parts:
        if p == "--history":
            history = True
        elif p == "--json":
            as_json = True
        elif p.startswith("--n="):
            with suppress(ValueError):
                n = int(p[4:])
        elif not p.startswith("--"):
            path = p
    return _StateArgs(path=path, history=history, as_json=as_json, n=n)
