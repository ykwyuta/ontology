"""漢数字の変換。"""
from __future__ import annotations

DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = {"十": 10, "百": 100, "千": 1000}
KANJI_NUM_CHARS = "".join(DIGITS) + "".join(UNITS)


def kanji_to_int(s: str) -> int:
    """「九十五」→95、「千四十四」→1044、「二〇」→20（位取り表記も可）。"""
    if not s:
        raise ValueError("empty")
    if all(c in DIGITS for c in s):
        return int("".join(str(DIGITS[c]) for c in s))
    total, cur = 0, 0
    for c in s:
        if c in DIGITS:
            cur = DIGITS[c]
        elif c in UNITS:
            total += (cur or 1) * UNITS[c]
            cur = 0
        else:
            raise ValueError(f"not a kanji numeral: {s!r}")
    return total + cur


def kanji_num_path(s: str) -> str:
    """「九十八条の二」の数字部分「九十八の二」→ "98_2"（法令XMLの Num 属性と同じ形）。"""
    return "_".join(str(kanji_to_int(p)) for p in s.split("の"))
