"""将棋のルール判定の試作（docs/proposal/shogi/prototype/schema.tql）を TypeDB で確かめる。

確かめること:
  1. 初期局面の先手の指し手が 30 通り（将棋の perft(1) = 30）
  2. 飛車・角・香の利きが、駒にぶつかったところで止まる
  3. 王手の判定
  4. 二歩の判定

使い方: python scripts/verify_shogi_prototype.py [--keep]
"""
import sys
from pathlib import Path

from typedb.driver import Credentials, DriverOptions, DriverTlsConfig, TransactionType, TypeDB

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/proposal/shogi/prototype/schema.tql"
DB = "shogi-prototype"

GOLD = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (0, 1)]
KING = [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if (x, y) != (0, 0)]
DIAG = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
ORTH = [(0, -1), (-1, 0), (1, 0), (0, 1)]
# 駒コード: (名前, [(df, dr, slides)], 行き所のない段数)
PIECES = {
    "P": ("歩", [(0, -1, False)], 1),
    "L": ("香", [(0, -1, True)], 1),
    "N": ("桂", [(-1, -2, False), (1, -2, False)], 2),
    "S": ("銀", [(x, y, False) for x, y in [(-1, -1), (0, -1), (1, -1), (-1, 1), (1, 1)]], 0),
    "G": ("金", [(x, y, False) for x, y in GOLD], 0),
    "B": ("角", [(x, y, True) for x, y in DIAG], 0),
    "R": ("飛", [(x, y, True) for x, y in ORTH], 0),
    "K": ("玉", [(x, y, False) for x, y in KING], 0),
    "+P": ("と", [(x, y, False) for x, y in GOLD], 0),
    "+L": ("成香", [(x, y, False) for x, y in GOLD], 0),
    "+N": ("成桂", [(x, y, False) for x, y in GOLD], 0),
    "+S": ("成銀", [(x, y, False) for x, y in GOLD], 0),
    "+B": ("馬", [(x, y, True) for x, y in DIAG] + [(x, y, False) for x, y in ORTH], 0),
    "+R": ("竜", [(x, y, True) for x, y in ORTH] + [(x, y, False) for x, y in DIAG], 0),
}
BACK = ["L", "N", "S", "G", "K", "G", "S", "N", "L"]   # 9 筋から 1 筋へ


def initial_position() -> list[tuple[str, str, int, int]]:
    """(駒, 先後, 筋, 段)"""
    out = []
    for i, code in enumerate(BACK):
        f = 9 - i
        out += [(code, "sente", f, 9), (code, "gote", f, 1)]
    for f in range(1, 10):
        out += [("P", "sente", f, 7), ("P", "gote", f, 3)]
    out += [("R", "sente", 2, 8), ("B", "sente", 8, 8), ("R", "gote", 8, 2), ("B", "gote", 2, 2)]
    return out


DIRECTIONS = sorted({(x, y) for x, y in KING} | {(x, y) for x in (-1, 1) for y in (-2, 2)})   # 8 方向と桂の 4 方向


def insert_board() -> str:
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


def insert_rules() -> str:
    out = ['$sente isa player, has side "sente", has sign 1;', '$gote isa player, has side "gote", has sign -1;']
    for code, (name, steps, last) in PIECES.items():
        v = "$pt_" + code.replace("+", "x")
        out.append(f'{v} isa piece-type, has piece-code "{code}", has piece-name "{name}", has last-ranks-forbidden {last};')
        for i, (df, dr, sl) in enumerate(steps):
            out.append(f"{v}_{i} isa step, has df {df}, has dr {dr}, has slides {str(sl).lower()};"
                       f" movement (piece: {v}, step: {v}_{i});")
    for base in ("P", "L", "N", "S", "B", "R"):
        out.append(f"promotion (base: $pt_{base}, promoted: $pt_x{base});")
    return "insert\n" + "\n".join(out)


def insert_position(pid: str, to_move: str, pieces) -> str:
    match = ['$sente isa player, has side "sente";', '$gote isa player, has side "gote";']
    out = [f'$p isa position, has position-id "{pid}";', f"turn (position: $p, player: ${to_move});"]
    codes = {}
    for i, (code, side, f, r) in enumerate(pieces):
        if code not in codes:
            codes[code] = f"$c{len(codes)}"
            match.append(f'{codes[code]} isa piece-type, has piece-code "{code}";')
        match.append(f'$q{i} isa square, has square-id "{f}{r}";')
        out.append(f"occupancy (position: $p, square: $q{i}, piece: {codes[code]}, owner: ${side});")
    return "match\n" + "\n".join(match) + "\ninsert\n" + "\n".join(out)


def main() -> int:
    driver = TypeDB.driver("127.0.0.1:1729", Credentials("admin", "password"),
                           DriverOptions(DriverTlsConfig.disabled()))
    if driver.databases.contains(DB):
        driver.databases.get(DB).delete()
    driver.databases.create(DB)

    def run(q, tt=TransactionType.READ):
        with driver.transaction(DB, tt) as tx:
            ans = tx.query(q).resolve()
            rows = list(ans.as_concept_rows()) if ans.is_concept_rows() else []
            if tt != TransactionType.READ:
                tx.commit()
            return rows

    run(SCHEMA.read_text(encoding="utf-8"), TransactionType.SCHEMA)
    run(insert_board(), TransactionType.WRITE)
    run(insert_rules(), TransactionType.WRITE)
    run(insert_position("initial", "sente", initial_position()), TransactionType.WRITE)
    # 王手の局面: 後手玉 5一、先手飛 5五（間に駒なし）、先手玉 5九
    run(insert_position("check", "gote", [("K", "gote", 5, 1), ("R", "sente", 5, 5), ("K", "sente", 5, 9)]),
        TransactionType.WRITE)
    # 同じ配置で、間（5三）に後手の歩がいる局面
    run(insert_position("blocked", "gote", [("K", "gote", 5, 1), ("P", "gote", 5, 3), ("R", "sente", 5, 5),
                                            ("K", "sente", 5, 9)]), TransactionType.WRITE)

    ok = True

    def check(label, got, want):
        nonlocal ok
        mark = "OK  " if got == want else "FAIL"
        ok &= got == want
        print(f"{mark} {label}: {got} (expected {want})")

    rows = run('match $p isa position, has position-id "initial"; '
               'let $s, $t, $pt in board_moves($p);')
    check("初期局面の先手の指し手の数", len(rows), 30)

    def reach_count(pid, code):
        return len(run(f'''match $p isa position, has position-id "{pid}";
            $pt isa piece-type, has piece-code "{code}";
            occupancy (position: $p, square: $s, piece: $pt, owner: $pl);
            let $t in reach($p, $pl, $pt, $s);'''))

    # 利きには自分の駒がいるマスも含む: 2八の飛車は 上 2七・下 2九・左 3八〜8八（6）・右 1八 で 9
    check("初期局面の飛車の利き（両者の飛車の合計）", reach_count("initial", "R"), 18)
    # 5五の飛車: 上 5四〜5一（4、5一の後手玉で止まる）・下 5六〜5九（4、5九の自玉を含む）・横 8 で 16
    check("5五の飛車の利き", reach_count("check", "R"), 16)

    def in_check(pid, side):
        return bool(run(f'''match $p isa position, has position-id "{pid}";
            $pl isa player, has side "{side}"; let $x in in_check($p, $pl);'''))

    check("後手玉に王手（5五の飛車）", in_check("check", "gote"), True)
    check("間に歩があれば王手ではない", in_check("blocked", "gote"), False)
    check("初期局面で先手玉に王手はない", in_check("initial", "sente"), False)

    def pawn_on_file(pid, side, f):
        return bool(run(f'''match $p isa position, has position-id "{pid}";
            $pl isa player, has side "{side}"; let $x in pawn_on_file($p, $pl, {f});'''))

    check("二歩: 初期局面の先手 5 筋に歩がある", pawn_on_file("initial", "sente", 5), True)
    check("二歩: 'blocked' の局面の先手 5 筋に歩はない", pawn_on_file("blocked", "sente", 5), False)

    if "--keep" not in sys.argv:
        driver.databases.get(DB).delete()
    driver.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
