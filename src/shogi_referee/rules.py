"""ルール層のデータ: 駒の動き、成りの対応、行き所のない駒、反則のルール。"""
from __future__ import annotations

GOLD = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (0, 1)]
KING = [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if (x, y) != (0, 0)]
DIAG = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
ORTH = [(0, -1), (-1, 0), (1, 0), (0, 1)]

# 駒コード（USI）: (名前, [(df, dr, 何マスでも進めるか)])。先手の向き（前 = dr -1）
PIECES: dict[str, tuple[str, list[tuple[int, int, bool]]]] = {
    "P": ("歩", [(0, -1, False)]),
    "L": ("香", [(0, -1, True)]),
    "N": ("桂", [(-1, -2, False), (1, -2, False)]),
    "S": ("銀", [(x, y, False) for x, y in [(-1, -1), (0, -1), (1, -1), (-1, 1), (1, 1)]]),
    "G": ("金", [(x, y, False) for x, y in GOLD]),
    "B": ("角", [(x, y, True) for x, y in DIAG]),
    "R": ("飛", [(x, y, True) for x, y in ORTH]),
    "K": ("玉", [(x, y, False) for x, y in KING]),
    "+P": ("と", [(x, y, False) for x, y in GOLD]),
    "+L": ("成香", [(x, y, False) for x, y in GOLD]),
    "+N": ("成桂", [(x, y, False) for x, y in GOLD]),
    "+S": ("成銀", [(x, y, False) for x, y in GOLD]),
    "+B": ("馬", [(x, y, True) for x, y in DIAG] + [(x, y, False) for x, y in ORTH]),
    "+R": ("竜", [(x, y, True) for x, y in ORTH] + [(x, y, False) for x, y in DIAG]),
}
PROMOTABLE = ["P", "L", "N", "S", "B", "R"]
HAND_PIECES = ["R", "B", "G", "S", "N", "L", "P"]          # 持ち駒になる駒（SFEN の並び順）
# 行き所のない駒: 先手から見て、いられない段
DEAD_END_RANKS = {"P": [1], "L": [1], "N": [1, 2]}
PROMOTION_ZONE = {"sente": [1, 2, 3], "gote": [7, 8, 9]}
# geometry に持たせる方向（8 方向と桂の 4 方向）
DIRECTIONS = sorted(set(KING) | {(x, y) for x in (-1, 1) for y in (-2, 2)})

SOURCE = "日本将棋連盟 対局規定（反則）— 条文との照合は未了"
# ルール ID: (名前, 説明)
RULES: dict[str, tuple[str, str]] = {
    "R-FORMAT": ("指し手の書式", "指し手が USI 形式（例: 7g7f、8h2b+、P*5e）として解析できない"),
    "R-NO-PIECE": ("移動元に駒がない", "動かそうとしたマスに駒がない"),
    "R-TURN": ("手番", "手番の側の駒しか動かせない"),
    "R-OWN": ("自分の駒のマス", "自分の駒がいるマスには動けない"),
    "R-MOVE": ("駒の動き", "駒は、その駒の動きで行けるマスにしか動けない。飛車・角・香は途中に駒があれば止まる"),
    "R-PROMO-PIECE": ("成れない駒", "玉・金・成った駒は成れない"),
    "R-PROMO-ZONE": ("成れる場所", "成れるのは、移動元か移動先が敵陣（相手側の 3 段）のときだけ"),
    "R-PROMO-MANDATORY": ("行き所のない駒（移動）", "歩・香を最奥の段に、桂を奥 2 段に動かすときは成らなければならない"),
    "R-DROP-HAND": ("持ち駒", "持っていない駒は打てない"),
    "R-DROP-EMPTY": ("打つマス", "駒のいるマスには打てない"),
    "R-DEADEND-DROP": ("行き所のない駒（打つ）", "歩・香を最奥の段に、桂を奥 2 段に打てない"),
    "R-NIFU": ("二歩", "成っていない自分の歩がある筋に、歩を打てない"),
    "R-UCHIFUZUME": ("打ち歩詰め", "歩を打って相手の玉を詰ませてはならない（盤上の歩を進めて詰ませるのはよい）"),
    "R-SELF-CHECK": ("王手放置", "指した後に、自分の玉が相手の駒の利きにあってはならない"),
}
