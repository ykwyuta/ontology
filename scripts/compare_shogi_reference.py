"""TypeDB の審判と、基準の将棋ライブラリ（python-shogi、テスト専用）の全合法手を突き合わせる。

ランダムに対局を進めて局面を集め、各局面で両者の合法手の集合が一致するかを確かめる。
使い方: python scripts/compare_shogi_reference.py [局面の数] [乱数の種]
"""
import random
import sys
import time

import shogi

from legal_onto import db
from shogi_referee.referee import Referee
from shogi_referee.sfen import parse_sfen

DB = "shogi-compare"


def sample_positions(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        b = shogi.Board()
        for _ in range(rng.randint(1, 160)):
            moves = list(b.legal_moves)
            if not moves:
                break
            # 駒を取る手・王手・打つ手を少し優先して、持ち駒と王手のある局面を増やす
            weighted = [m for m in moves if b.piece_at(m.to_square) or m.drop_piece_type] or moves
            b.push(rng.choice(weighted if rng.random() < 0.5 else moves))
        # 半分は王手のかかった局面にする（王手への対応・ピン・打ち歩詰めの判定を多く通すため）
        if len(out) % 2 == 0 and not b.is_check():
            checks = []
            for m in b.legal_moves:
                b.push(m)
                if b.is_check():
                    checks.append(m)
                b.pop()
            if not checks:
                continue
            b.push(rng.choice(checks))
            if not list(b.legal_moves):
                continue
        out.append(b.sfen())
    return out


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    positions = sample_positions(n, seed)
    bad = 0
    t0 = time.time()
    with db.connect() as d:
        ref = Referee.create(d, DB, recreate=True)
        stats = {"check": 0, "hand": 0, "moves": 0}
        for i, sfen in enumerate(positions):
            expected = {m.usi() for m in shogi.Board(sfen).legal_moves}
            got = {m.usi for m in ref.legal_moves(parse_sfen(sfen))}
            b = shogi.Board(sfen)
            stats["check"] += b.is_check()
            stats["hand"] += any(b.pieces_in_hand[c] for c in (0, 1))
            stats["moves"] += len(expected)
            if got != expected:
                bad += 1
                print(f"MISMATCH {i}: {sfen}\n  missing: {sorted(expected - got)}\n  extra:   {sorted(got - expected)}")
        d.databases.get(DB).delete()
    print(f"{n - bad}/{n} positions match ({stats['moves']} legal moves; {stats['check']} in check; "
          f"{stats['hand']} with pieces in hand) in {time.time() - t0:.0f}s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
