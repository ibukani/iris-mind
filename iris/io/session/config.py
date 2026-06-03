from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    access_token: str = ""
