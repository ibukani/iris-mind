from __future__ import annotations

import re


class RepetitionDetector:
    """LLM 出力の繰り返しパターンを検出・トリミングする。

    マルチチャー（2-20文字のブロックが4回以上）とシングルチャー（1文字が10回以上）の
    2種類の繰り返しパターンを検出する。検出された繰り返しは省略記号＋注釈で置き換える。
    """

    _RE_MULTI_REPEAT = re.compile(r"(.{2,20}?)\1{3,}")
    _RE_SINGLE_REPEAT = re.compile(r"(.)\1{9,}")
    _RE_MULTI_REPEAT_FULL = re.compile(r"((.{2,20}?)\2{3,})")
    _RE_SINGLE_REPEAT_FULL = re.compile(r"((.)\2{9,})")

    def detect(self, text: str) -> bool:
        if not text:
            return False
        target = text[-150:] if len(text) > 150 else text
        for match in self._RE_MULTI_REPEAT.finditer(target):
            if len(set(match.group(1))) > 1:
                return True
        return bool(self._RE_SINGLE_REPEAT.search(target))

    def trim(self, text: str) -> str:
        for match_multi in self._RE_MULTI_REPEAT_FULL.finditer(text):
            pattern = match_multi.group(2)
            if len(set(pattern)) > 1:
                start = match_multi.start(1)
                replacement = pattern * 2 + "… [繰り返し検知により中断]"
                return text[:start] + replacement
        match_single = self._RE_SINGLE_REPEAT_FULL.search(text)
        if match_single:
            start = match_single.start(1)
            char = match_single.group(2)
            replacement = char * 3 + "… [繰り返し検知により中断]"
            return text[:start] + replacement
        return text
