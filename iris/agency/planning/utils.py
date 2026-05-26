from __future__ import annotations


def build_time_label() -> str:
    import time

    hour = time.localtime().tm_hour
    if hour < 12:
        return "午前"
    if hour < 17:
        return "午後"
    return "夕方以降"
