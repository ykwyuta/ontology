"""コマンドライン。

  shogi-referee init-db [--recreate]              データベースを作り、盤・駒・ルールのデータを入れる
  shogi-referee legal [SFEN]                      全合法手（SFEN を省略すると初期局面）
  shogi-referee judge SFEN MOVE                   指し手を判定し、結果を JSON で表示
  shogi-referee replay MOVE... [--start SFEN] [--mode strict|retry] [--max-moves N]
                                                  指し手を順に審判し、対局の記録を JSON で表示
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from legal_onto import db

from .game import Game
from .referee import DATABASE, Referee
from .sfen import INITIAL, parse_sfen

DB = os.environ.get("SHOGI_DATABASE", DATABASE)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shogi-referee")
    ap.add_argument("--database", default=DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init-db")
    p.add_argument("--recreate", action="store_true")
    p = sub.add_parser("legal")
    p.add_argument("sfen", nargs="?", default=INITIAL)
    p = sub.add_parser("judge")
    p.add_argument("sfen")
    p.add_argument("move")
    p = sub.add_parser("replay")
    p.add_argument("moves", nargs="*")
    p.add_argument("--start", default=INITIAL)
    p.add_argument("--mode", choices=["strict", "retry"], default="strict")
    p.add_argument("--max-moves", type=int, default=256)
    a = ap.parse_args(argv)

    with db.connect() as driver:
        if a.cmd == "init-db":
            Referee.create(driver, a.database, recreate=a.recreate)
            print(f"initialized database {a.database!r}")
            return 0
        ref = Referee.create(driver, a.database)
        if a.cmd == "legal":
            moves = ref.legal_moves(parse_sfen(a.sfen))
            print(f"{len(moves)} legal moves")
            print(" ".join(m.usi for m in moves))
        elif a.cmd == "judge":
            j = ref.judge(a.sfen, a.move)
            _print(j.as_dict())
            return 0 if j.legal else 1
        elif a.cmd == "replay":
            g = Game(ref, mode=a.mode, max_moves=a.max_moves, start=a.start)
            for m in a.moves:
                if g.over:
                    break
                g.play(m)
            _print(g.record())
    return 0


if __name__ == "__main__":
    sys.exit(main())
