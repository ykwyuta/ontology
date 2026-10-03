"""TypeDB 上の将棋のルールで、合法手の生成と指し手の判定を行う。

ルールの判断はすべて TypeDB の関数（schema/shogi/schema.tql）で行う。このモジュールが行うのは手順だけ:
  - 局面（SFEN）を TypeDB に書き込む
  - 合法手の関数を呼び、結果を USI に変換する
  - 打ち歩詰めの判定のために、歩を打った後の局面を書き込んで、相手の合法手があるかを問い合わせる
  - 合法手にない指し手について、反則ごとの関数を呼んで理由を特定する
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

from typedb.driver import Driver, TransactionType

from .rules import DEAD_END_RANKS, DIRECTIONS, PIECES, PROMOTABLE, PROMOTION_ZONE, RULES, SOURCE
from .sfen import Move, Position, SfenError, apply_move, parse_sfen, parse_usi, square_ja, to_sfen

SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "shogi" / "schema.tql"
DATABASE = "shogi"
PIECE_JA = {code: name for code, (name, _) in PIECES.items()}


@dataclass
class Violation:
    rule: str
    reason: str

    def as_dict(self) -> dict:
        label, text = RULES[self.rule]
        return {"rule": self.rule, "label": label, "reason": self.reason, "rule_text": text, "source": SOURCE}


@dataclass
class Judgement:
    move: str
    sfen: str
    legal: bool
    violations: list[Violation] = field(default_factory=list)
    legal_moves: list[str] = field(default_factory=list)

    def as_dict(self, examples: int = 5) -> dict:
        return {"move": self.move, "legal": self.legal, "position": self.sfen,
                "violations": [v.as_dict() for v in self.violations],
                "legal_move_count": len(self.legal_moves),
                "legal_move_examples": self.legal_moves[:examples]}


class Referee:
    def __init__(self, driver: Driver, database: str = DATABASE):
        self.driver = driver
        self.db = database
        self._counter = itertools.count()
        self._load_ids()

    # ---------- データベースの準備 ----------

    @classmethod
    def create(cls, driver: Driver, database: str = DATABASE, *, recreate: bool = False) -> "Referee":
        if driver.databases.contains(database):
            if not recreate:
                return cls(driver, database)
            driver.databases.get(database).delete()
        driver.databases.create(database)
        with driver.transaction(database, TransactionType.SCHEMA) as tx:
            tx.query(SCHEMA.read_text(encoding="utf-8")).resolve()
            tx.commit()
        with driver.transaction(database, TransactionType.WRITE) as tx:
            tx.query(_insert_board()).resolve()
            tx.query(_insert_rules()).resolve()
            tx.query(_insert_zones()).resolve()
            tx.commit()
        return cls(driver, database)

    def _rows(self, query: str) -> list:
        with self.driver.transaction(self.db, TransactionType.READ) as tx:
            return list(tx.query(query).resolve().as_concept_rows())

    def _load_ids(self) -> None:
        self.square_iid, self.iid_square = {}, {}
        for r in self._rows("match $s isa square, has file $f, has rank $r;"):
            sq = (r.get("f").get_value(), r.get("r").get_value())
            iid = r.get("s").get_iid()
            self.square_iid[sq], self.iid_square[iid] = iid, sq
        self.piece_iid, self.iid_piece = {}, {}
        for r in self._rows("match $p isa piece-type, has piece-code $c;"):
            self.piece_iid[r.get("c").get_value()] = r.get("p").get_iid()
            self.iid_piece[r.get("p").get_iid()] = r.get("c").get_value()
        self.player_iid = {r.get("s").get_value(): r.get("p").get_iid()
                           for r in self._rows("match $p isa player, has side $s;")}
        if len(self.square_iid) != 81:
            raise RuntimeError(f"database {self.db!r} is not initialised (Referee.create)")

    # ---------- 局面 ----------

    def store(self, pos: Position) -> str:
        """局面を書き込み、position-id を返す。"""
        pid = f"p{next(self._counter)}-{id(self)}"
        match = [f"$sente iid {self.player_iid['sente']}; $sente isa player;",
                 f"$gote iid {self.player_iid['gote']}; $gote isa player;"]
        out = [f'$p isa position, has position-id "{pid}", has sfen "{to_sfen(pos, with_ply=False)}";',
               f"turn (position: $p, player: ${pos.side});"]
        pieces = {}

        def piece_var(code: str) -> str:
            if code not in pieces:
                pieces[code] = f"$c{len(pieces)}"
                match.append(f"{pieces[code]} iid {self.piece_iid[code]}; {pieces[code]} isa piece-type;")
            return pieces[code]

        for i, (sq, (code, side)) in enumerate(pos.board.items()):
            match.append(f"$q{i} iid {self.square_iid[sq]}; $q{i} isa square;")
            out.append(f"occupancy (position: $p, square: $q{i}, piece: {piece_var(code)}, owner: ${side});")
        for side, hand in pos.hands.items():
            for code, n in hand.items():
                if n > 0:
                    out.append(f"in-hand (position: $p, piece: {piece_var(code)}, owner: ${side}), has amount {n};")
        with self.driver.transaction(self.db, TransactionType.WRITE) as tx:
            tx.query("match " + " ".join(match) + "\ninsert " + "\n".join(out)).resolve()
            tx.commit()
        return pid

    def delete(self, pid: str) -> None:
        with self.driver.transaction(self.db, TransactionType.WRITE) as tx:
            tx.query(f'match $p isa position, has position-id "{pid}"; delete $p;').resolve()
            tx.commit()

    # ---------- 合法手 ----------

    def _pos(self, pid: str) -> str:
        return f'$p isa position, has position-id "{pid}";'

    def _legal_in_db(self, pid: str) -> tuple[list[Move], list[Move]]:
        """(盤上の移動と、打ち歩詰めを除く前の打つ手)"""
        moves = []
        for fn, promote in (("legal_moves_unpromoted", False), ("legal_moves_promoted", True)):
            for r in self._rows(f"match {self._pos(pid)} let $s, $t, $pt in {fn}($p);"):
                moves.append(Move(to=self.iid_square[r.get("t").get_iid()],
                                  frm=self.iid_square[r.get("s").get_iid()], promote=promote))
        drops = [Move(to=self.iid_square[r.get("t").get_iid()], drop=self.iid_piece[r.get("pt").get_iid()])
                 for r in self._rows(f"match {self._pos(pid)} let $pt, $t in legal_drops($p);")]
        return moves, drops

    def _has_legal_move(self, pid: str) -> bool:
        for fn in ("legal_moves_unpromoted", "legal_moves_promoted"):
            if self._rows(f"match {self._pos(pid)} let $s, $t, $pt in {fn}($p); limit 1;"):
                return True
        return bool(self._rows(f"match {self._pos(pid)} let $pt, $t in legal_drops($p); limit 1;"))

    def _pawn_drop_checks(self, pid: str, to: tuple[int, int]) -> bool:
        return bool(self._rows(f"""match {self._pos(pid)} $t iid {self.square_iid[to]}; $t isa square;
                                   let $x in pawn_drop_checks($p, $t);"""))

    def is_uchifuzume(self, pos: Position, pid: str, move: Move) -> bool:
        """歩を打って王手になり、相手に合法手がない（詰み）なら打ち歩詰め。後の局面を書き込んで確かめる。"""
        if move.drop != "P" or not self._pawn_drop_checks(pid, move.to):
            return False
        after = self.store(apply_move(pos, move))
        try:
            return not self._has_legal_move(after)
        finally:
            self.delete(after)

    def legal_moves(self, pos: Position, pid: str | None = None) -> list[Move]:
        own = pid is None
        pid = pid or self.store(pos)
        try:
            moves, drops = self._legal_in_db(pid)
            drops = [m for m in drops if not self.is_uchifuzume(pos, pid, m)]
            return sorted(moves + drops, key=lambda m: m.usi)
        finally:
            if own:
                self.delete(pid)

    def is_checkmate(self, pos: Position) -> bool:
        pid = self.store(pos)
        try:
            return not self.legal_moves(pos, pid)
        finally:
            self.delete(pid)

    # ---------- 指し手の判定 ----------

    def in_check(self, pos: Position, side: str) -> bool:
        pid = self.store(pos)
        try:
            return bool(self._rows(f"""match {self._pos(pid)} $pl iid {self.player_iid[side]}; $pl isa player;
                                       let $x in in_check($p, $pl);"""))
        finally:
            self.delete(pid)

    def judge_move(self, pos: Position, usi: str, legal: list[str]) -> Judgement:
        """合法手の一覧（求めてあるもの）を使って判定する。合法手にない指し手は、反則ごとの関数で理由を特定する。"""
        j = Judgement(usi, to_sfen(pos), False, legal_moves=legal)
        try:
            move = parse_usi(usi)
        except SfenError:
            j.violations.append(Violation("R-FORMAT", f"「{usi}」は USI の指し手として解析できない"))
            return j
        if move.usi in legal:
            j.legal = True
            return j
        pid = self.store(pos)
        try:
            j.violations = self._explain(pos, pid, move) or [
                Violation("R-MOVE", "合法手の一覧にない（理由を特定できなかった）")]
        finally:
            self.delete(pid)
        return j

    def judge(self, sfen: str, usi: str) -> Judgement:
        pos = parse_sfen(sfen)
        pid = self.store(pos)
        try:
            legal = self.legal_moves(pos, pid)
            usis = [m.usi for m in legal]
            j = Judgement(usi, to_sfen(pos), False, legal_moves=usis)
            try:
                move = parse_usi(usi)
            except SfenError:
                j.violations.append(Violation("R-FORMAT", f"「{usi}」は USI の指し手として解析できない"))
                return j
            if move.usi in usis:
                j.legal = True
                return j
            j.violations = self._explain(pos, pid, move) or [
                Violation("R-MOVE", "合法手の一覧にない（理由を特定できなかった）")]
            return j
        finally:
            self.delete(pid)

    def _check(self, pid: str, fn: str, **args) -> bool:
        binds, params = [], []
        for name, (kind, value) in args.items():
            iid = {"square": self.square_iid, "piece": self.piece_iid}[kind][value]
            binds.append(f"${name} iid {iid}; ${name} isa {'square' if kind == 'square' else 'piece-type'};")
            params.append(f"${name}")
        q = f"match {self._pos(pid)} {' '.join(binds)} let $x in {fn}($p, {', '.join(params)});"
        return bool(self._rows(q))

    def _explain(self, pos: Position, pid: str, move: Move) -> list[Violation]:
        me = "先手" if pos.side == "sente" else "後手"
        t = move.to
        out: list[Violation] = []
        if move.drop:
            name = PIECE_JA[move.drop]
            if self._check(pid, "v_drop_hand", pt=("piece", move.drop)):
                return [Violation("R-DROP-HAND", f"{me}の持ち駒に{name}がない")]
            if self._check(pid, "v_drop_empty", t=("square", t)):
                return [Violation("R-DROP-EMPTY", f"{square_ja(t)}には駒がある")]
            if self._check(pid, "v_deadend_drop", pt=("piece", move.drop), t=("square", t)):
                out.append(Violation("R-DEADEND-DROP", f"{square_ja(t)}に{name}を打つと、行き所がない"))
            if self._check(pid, "v_nifu", pt=("piece", move.drop), t=("square", t)):
                pawn = next(sq for sq, (c, s) in pos.board.items() if c == "P" and s == pos.side and sq[0] == t[0])
                out.append(Violation("R-NIFU", f"{t[0]}筋に{me}の歩（{square_ja(pawn)}）があるため、{t[0]}筋に歩を打てない"))
            if self._check(pid, "v_self_check", f=("square", t), t=("square", t), pt=("piece", move.drop)):
                out.append(Violation("R-SELF-CHECK", f"{square_ja(t)}に{name}を打っても、{me}の玉への王手が残る"))
            if not out and self.is_uchifuzume(pos, pid, move):
                out.append(Violation("R-UCHIFUZUME", f"{square_ja(t)}に歩を打つと相手の玉が詰む（打ち歩詰め）"))
            return out

        f = move.frm
        if self._check(pid, "v_no_piece", f=("square", f)):
            return [Violation("R-NO-PIECE", f"{square_ja(f)}に駒がない")]
        code, owner = pos.board[f]
        name = PIECE_JA[code]
        if self._check(pid, "v_turn", f=("square", f)):
            return [Violation("R-TURN", f"{square_ja(f)}の{name}は相手の駒（手番は{me}）")]
        if self._check(pid, "v_own", t=("square", t)):
            out.append(Violation("R-OWN", f"{square_ja(t)}には{me}の駒がある"))
        if self._check(pid, "v_move", f=("square", f), t=("square", t)):
            out.append(Violation("R-MOVE", f"{square_ja(f)}の{name}は{square_ja(t)}に動けない"))
        if move.promote:
            if self._check(pid, "v_promo_piece", f=("square", f)):
                out.append(Violation("R-PROMO-PIECE", f"{name}は成れない"))
            elif self._check(pid, "v_promo_zone", f=("square", f), t=("square", t)):
                out.append(Violation("R-PROMO-ZONE", f"{square_ja(f)}も{square_ja(t)}も敵陣ではないので成れない"))
        elif self._check(pid, "v_promo_mandatory", f=("square", f), t=("square", t)):
            out.append(Violation("R-PROMO-MANDATORY", f"{square_ja(t)}に{name}を成らずに動かすと、行き所がない"))
        if not out and self._check(pid, "v_self_check", f=("square", f), t=("square", t), pt=("piece", code)):
            out.append(Violation("R-SELF-CHECK", f"{square_ja(f)}の{name}を{square_ja(t)}に動かすと、{me}の玉に王手がかかる"))
        return out


# ---------- 初期データ ----------

def _insert_board() -> str:
    out = []
    for f in range(1, 10):
        for r in range(1, 10):
            out.append(f'$s{f}{r} isa square, has square-id "{f}{r}", has file {f}, has rank {r};')
    for f in range(1, 10):
        for r in range(1, 10):
            for df, dr in DIRECTIONS:
                if 1 <= f + df <= 9 and 1 <= r + dr <= 9:
                    out.append(f"geometry (origin: $s{f}{r}, target: $s{f + df}{r + dr}), has df {df}, has dr {dr};")
    return "insert\n" + "\n".join(out)


def _pv(code: str) -> str:
    return "$pt_" + code.replace("+", "x")


def _insert_rules() -> str:
    out = ['$sente isa player, has side "sente", has sign 1;', '$gote isa player, has side "gote", has sign -1;']
    for code, (name, steps) in PIECES.items():
        out.append(f'{_pv(code)} isa piece-type, has piece-code "{code}", has piece-name "{name}";')
        for i, (df, dr, sl) in enumerate(steps):
            out.append(f"{_pv(code)}_{i} isa step, has df {df}, has dr {dr}, has slides {str(sl).lower()};"
                       f" movement (piece: {_pv(code)}, step: {_pv(code)}_{i});")
    for base in PROMOTABLE:
        out.append(f"promotion (base: {_pv(base)}, promoted: {_pv('+' + base)});")
    for rid, (label, text) in RULES.items():
        out.append(f'$rule_{rid.replace("-", "_")} isa rule, has rule-id "{rid}", has rule-label "{label}", '
                   f'has rule-text "{text}", has source-ref "{SOURCE}";')
    return "insert\n" + "\n".join(out)


def _insert_zones() -> str:
    match = ['$sente isa player, has side "sente";', '$gote isa player, has side "gote";']
    for code in DEAD_END_RANKS:
        match.append(f'{_pv(code)} isa piece-type, has piece-code "{code}";')
    out = []
    for f in range(1, 10):
        for r in range(1, 10):
            match.append(f'$s{f}{r} isa square, has square-id "{f}{r}";')
            for side, ranks in PROMOTION_ZONE.items():
                if r in ranks:
                    out.append(f"promotion-zone (player: ${side}, square: $s{f}{r});")
            for code, ranks in DEAD_END_RANKS.items():
                if r in ranks:
                    out.append(f"dead-end (player: $sente, piece: {_pv(code)}, square: $s{f}{r});")
                if (10 - r) in ranks:
                    out.append(f"dead-end (player: $gote, piece: {_pv(code)}, square: $s{f}{r});")
    return "match\n" + "\n".join(match) + "\ninsert\n" + "\n".join(out)
