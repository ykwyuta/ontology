"""対局の審判: 指し手を順に判定し、対局の終了を判定する（docs/proposal/shogi/06-decisions.md 6.2）。

モード:
  strict  公式ルールどおり、反則の指し手を指した側の負け
  retry   反則なら理由を返して指し直させる（評価用）。上限回数を超えたら反則負け
終了:
  詰み（合法手がない）、反則、連続王手の千日手、千日手、最大手数、投了
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .referee import Judgement, Referee
from .sfen import INITIAL, Position, apply_move, parse_sfen, parse_usi, to_sfen

SIDE_JA = {"sente": "先手", "gote": "後手"}


def other(side: str) -> str:
    return "gote" if side == "sente" else "sente"


@dataclass
class Result:
    winner: str | None          # "sente" / "gote" / None（引き分け）
    reason: str                 # "checkmate", "illegal", "perpetual-check", "repetition", "max-moves", "resign"
    detail: str = ""

    def as_dict(self) -> dict:
        return {"winner": self.winner, "reason": self.reason, "detail": self.detail}


@dataclass
class Attempt:
    ply: int
    side: str
    move: str
    judgement: Judgement


@dataclass
class Game:
    referee: Referee
    mode: str = "strict"
    max_moves: int = 256
    max_retries: int = 3
    start: str = INITIAL
    position: Position = field(init=False)
    moves: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    result: Result | None = None
    _keys: list[str] = field(default_factory=list)       # 各局面（盤・持ち駒・手番）の SFEN
    _checks: list[bool] = field(default_factory=list)    # 各手が王手だったか
    _legal: list[str] = field(default_factory=list)
    _retries: int = 0

    def __post_init__(self) -> None:
        if self.mode not in ("strict", "retry"):
            raise ValueError("mode は strict か retry")
        self.position = parse_sfen(self.start)
        self._start_side = self.position.side
        self._keys.append(to_sfen(self.position, with_ply=False))
        self._legal = self._legal_moves()
        if not self._legal:
            self.result = Result(other(self.position.side), "checkmate", "開始局面で手番の側に合法手がない")

    def _legal_moves(self) -> list[str]:
        return [m.usi for m in self.referee.legal_moves(self.position)]

    @property
    def over(self) -> bool:
        return self.result is not None

    @property
    def legal_moves(self) -> list[str]:
        return list(self._legal)

    def play(self, usi: str) -> Judgement | None:
        """手番の側の指し手を 1 つ判定し、合法なら局面を進める。投了は "resign"。"""
        if self.over:
            raise RuntimeError("対局は終了している")
        side = self.position.side
        if usi.strip().lower() == "resign":
            self.result = Result(other(side), "resign", f"{SIDE_JA[side]}が投了")
            return None
        j = self.referee.judge_move(self.position, usi, self._legal)
        self.attempts.append(Attempt(self.position.ply, side, usi, j))
        if not j.legal:
            self._retries += 1
            if self.mode == "strict" or self._retries > self.max_retries:
                rules = "、".join(v.rule for v in j.violations)
                self.result = Result(other(side), "illegal", f"{SIDE_JA[side]}の反則（{rules}）: {usi}")
            return j

        self._retries = 0
        self.position = apply_move(self.position, parse_usi(usi))
        self.moves.append(usi)
        self._keys.append(to_sfen(self.position, with_ply=False))
        self._checks.append(self.referee.in_check(self.position, self.position.side))
        self._judge_end(side)
        return j

    def _side_of(self, i: int) -> str:
        """i 番目（0 始まり）の手を指した側。"""
        return self._start_side if i % 2 == 0 else other(self._start_side)

    def _judge_end(self, mover: str) -> None:
        key = self._keys[-1]
        occurrences = [i for i, k in enumerate(self._keys) if k == key]
        if len(occurrences) >= 4:
            # 同一局面の 1 回目（4 回のうち最初）から現在までの手について、一方の手がすべて王手なら連続王手の千日手
            span = range(occurrences[-4], len(self.moves))
            for side in ("sente", "gote"):
                mine = [i for i in span if self._side_of(i) == side]
                if mine and all(self._checks[i] for i in mine):
                    self.result = Result(other(side), "perpetual-check",
                                         f"{SIDE_JA[side]}の連続王手の千日手（同一局面 4 回）")
                    return
            self.result = Result(None, "repetition", "千日手（同一局面 4 回）")
            return
        self._legal = self._legal_moves()
        if not self._legal:
            self.result = Result(mover, "checkmate", f"{SIDE_JA[other(mover)]}に合法手がない（詰み）")
            return
        if len(self.moves) >= self.max_moves:
            self.result = Result(None, "max-moves", f"{self.max_moves} 手に達した")

    def record(self) -> dict:
        return {"start": self.start, "mode": self.mode, "moves": self.moves,
                "result": self.result.as_dict() if self.result else None,
                "attempts": [{"ply": a.ply, "side": a.side, "move": a.move, "legal": a.judgement.legal,
                              "violations": [v.rule for v in a.judgement.violations]} for a in self.attempts]}
