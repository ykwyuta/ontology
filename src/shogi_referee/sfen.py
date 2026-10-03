"""SFEN（局面）と USI（指し手）の解析・生成と、指し手の適用（駒の移動・取った駒・成り）。

ルールの判断（合法かどうか）はここでは行わない。それは TypeDB の関数の役割。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rules import HAND_PIECES

INITIAL = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
RANKS = "abcdefghi"
SIDES = ("sente", "gote")


@dataclass
class Position:
    board: dict[tuple[int, int], tuple[str, str]]          # (筋, 段) -> (駒コード, 先後)
    hands: dict[str, dict[str, int]] = field(default_factory=lambda: {"sente": {}, "gote": {}})
    side: str = "sente"
    ply: int = 1

    def copy(self) -> "Position":
        return Position(dict(self.board), {s: dict(h) for s, h in self.hands.items()}, self.side, self.ply)


@dataclass(frozen=True)
class Move:
    to: tuple[int, int]
    frm: tuple[int, int] | None = None        # None なら打つ手
    drop: str | None = None                   # 打つ駒のコード
    promote: bool = False

    @property
    def usi(self) -> str:
        t = square_usi(self.to)
        if self.drop:
            return f"{self.drop}*{t}"
        return f"{square_usi(self.frm)}{t}{'+' if self.promote else ''}"


def square_usi(sq: tuple[int, int]) -> str:
    return f"{sq[0]}{RANKS[sq[1] - 1]}"


def square_ja(sq: tuple[int, int]) -> str:
    return f"{sq[0]}{'一二三四五六七八九'[sq[1] - 1]}"


class SfenError(ValueError):
    pass


def parse_sfen(text: str) -> Position:
    parts = text.strip().split()
    if parts and parts[0] == "sfen":
        parts = parts[1:]
    if len(parts) < 3:
        raise SfenError(f"SFEN が短い: {text!r}")
    rows = parts[0].split("/")
    if len(rows) != 9:
        raise SfenError("SFEN の盤は 9 段")
    board = {}
    for r, row in enumerate(rows, start=1):
        f, promoted = 9, False
        for ch in row:
            if ch.isdigit():
                f -= int(ch)
            elif ch == "+":
                promoted = True
            else:
                code = ("+" if promoted else "") + ch.upper()
                board[(f, r)] = (code, "sente" if ch.isupper() else "gote")
                f -= 1
                promoted = False
        if f != 0:
            raise SfenError(f"SFEN の {r} 段目のマスの数が 9 ではない")
    side = {"b": "sente", "w": "gote"}.get(parts[1])
    if side is None:
        raise SfenError("手番は b か w")
    hands = {"sente": {}, "gote": {}}
    if parts[2] != "-":
        for n, ch in re.findall(r"(\d*)([RBGSNLPrbgsnlp])", parts[2]):
            hands["sente" if ch.isupper() else "gote"][ch.upper()] = int(n or 1)
    ply = int(parts[3]) if len(parts) > 3 else 1
    return Position(board, hands, side, ply)


def to_sfen(pos: Position, *, with_ply: bool = True) -> str:
    rows = []
    for r in range(1, 10):
        row, empty = "", 0
        for f in range(9, 0, -1):
            if (f, r) in pos.board:
                code, side = pos.board[(f, r)]
                if empty:
                    row += str(empty)
                    empty = 0
                row += code if side == "sente" else code.lower()
            else:
                empty += 1
        rows.append(row + (str(empty) if empty else ""))
    hand = ""
    for side in SIDES:
        for code in HAND_PIECES:
            n = pos.hands[side].get(code, 0)
            if n:
                c = code if side == "sente" else code.lower()
                hand += (str(n) if n > 1 else "") + c
    s = f"{'/'.join(rows)} {'b' if pos.side == 'sente' else 'w'} {hand or '-'}"
    return f"{s} {pos.ply}" if with_ply else s


USI_RE = re.compile(r"^(?:([1-9][a-i])([1-9][a-i])(\+)?|([RBGSNLP])\*([1-9][a-i]))$")


def parse_usi(text: str) -> Move:
    m = USI_RE.match(text.strip())
    if not m:
        raise SfenError(f"USI の指し手として解析できない: {text!r}")

    def sq(s: str) -> tuple[int, int]:
        return int(s[0]), RANKS.index(s[1]) + 1

    if m.group(4):
        return Move(to=sq(m.group(5)), drop=m.group(4))
    return Move(to=sq(m.group(2)), frm=sq(m.group(1)), promote=bool(m.group(3)))


def apply_move(pos: Position, move: Move) -> Position:
    """指し手を適用した局面（合法かどうかは確かめない）。"""
    new = pos.copy()
    me = pos.side
    if move.drop:
        new.hands[me][move.drop] -= 1
        if not new.hands[me][move.drop]:
            del new.hands[me][move.drop]
        new.board[move.to] = (move.drop, me)
    else:
        code, owner = new.board.pop(move.frm)
        captured = new.board.get(move.to)
        if captured:
            base = captured[0].lstrip("+")
            new.hands[me][base] = new.hands[me].get(base, 0) + 1
        new.board[move.to] = (("+" + code) if move.promote else code, owner)
    new.side = "gote" if me == "sente" else "sente"
    new.ply += 1
    return new
