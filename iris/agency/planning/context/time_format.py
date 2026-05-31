from __future__ import annotations

from datetime import UTC, datetime


def format_age(ts: str) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, OverflowError):
        return ""
    diff = datetime.now(UTC) - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "たった今"
    if secs < 3600:
        return f"{secs // 60}分前"
    if secs < 86400:
        return f"{secs // 3600}時間前"
    days = secs // 86400
    return f"{days}日前" if days > 1 else "昨日"
