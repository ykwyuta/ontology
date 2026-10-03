"""ルールごとの判定（TypeDB が必要）。期待する合法・反則は、基準のライブラリ（python-shogi）でも確かめる。"""
import pytest

from legal_onto import db
from shogi_referee.referee import Referee
from shogi_referee.sfen import INITIAL, parse_sfen

shogi = pytest.importorskip("shogi")
pytestmark = pytest.mark.typedb
TEST_DB = "shogi-test"

EMPTY_KINGS = "4k4/9/9/9/9/9/9/9/4K4"
CASES = [
    # (局面, 指し手, 期待: None なら合法、ルール ID なら反則)
    (INITIAL, "7g7f", None),
    (INITIAL, "7g7e", "R-MOVE"),
    (INITIAL, "5e5d", "R-NO-PIECE"),
    (INITIAL, "3c3d", "R-TURN"),
    (INITIAL, "2h2g", "R-OWN"),
    (INITIAL, "5g5f+", "R-PROMO-ZONE"),
    (INITIAL, "P*5e", "R-DROP-HAND"),
    (INITIAL, "7g7f7", "R-FORMAT"),
    ("lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b P 1", "P*5e", "R-NIFU"),
    ("4k4/9/9/9/4+P4/9/9/9/4K4 b P 1", "P*5c", None),                 # と金は二歩に数えない
    (f"{EMPTY_KINGS} b P 1", "P*1a", "R-DEADEND-DROP"),
    (f"{EMPTY_KINGS} b N 1", "N*1b", "R-DEADEND-DROP"),
    (f"{EMPTY_KINGS} b N 1", "N*1c", None),
    (f"{EMPTY_KINGS} b G 1", "G*5i", "R-DROP-EMPTY"),
    ("4k4/8P/9/9/9/9/9/9/4K4 b - 1", "1b1a", "R-PROMO-MANDATORY"),
    ("4k4/8P/9/9/9/9/9/9/4K4 b - 1", "1b1a+", None),
    ("4k4/9/9/9/9/9/9/4G4/4K4 b - 1", "5h5g+", "R-PROMO-PIECE"),
    ("4k4/9/9/9/9/9/9/9/P3K4 b - 1", "9i9h+", "R-PROMO-ZONE"),
    ("4k4/9/9/9/9/9/9/9/4K4 b - 1", "5i4h", None),
    ("4r3k/9/9/9/9/9/9/4G4/4K4 b - 1", "5h4h", "R-SELF-CHECK"),       # ピンされた金
    ("4r3k/9/9/9/9/9/9/4G4/4K4 b - 1", "5h5g", None),                 # 同じ筋なら動ける
    ("k3r4/9/9/9/9/9/9/9/3K5 b - 1", "6i5i", "R-SELF-CHECK"),         # 自分から利きに入る
    ("7nk/9/7G1/9/9/9/9/9/K8 b P 1", "P*1b", "R-UCHIFUZUME"),
    ("8k/9/8G/9/9/9/9/9/K8 b P 1", "P*1b", None),                    # 逃げ道があれば打ち歩詰めではない
    ("7nk/7P1/7G1/9/9/9/9/9/K8 b - 1", "2b2a+", None),               # 盤上の歩で詰ませる（突き歩詰め）はよい
]


@pytest.fixture(scope="module")
def ref():
    try:
        with db.connect() as d:
            d.databases.all()
            yield Referee.create(d, TEST_DB, recreate=True)
            d.databases.get(TEST_DB).delete()
    except Exception as e:  # noqa: BLE001
        if "connect" in str(e).lower():
            pytest.skip(f"TypeDB に接続できない: {e}")
        raise


def reference_is_legal(sfen: str, usi: str) -> bool:
    try:
        move = shogi.Move.from_usi(usi)
    except ValueError:
        return False
    return move in shogi.Board(sfen).legal_moves


@pytest.mark.parametrize("sfen,usi,expected", CASES, ids=[f"{c[1]}-{c[2] or 'legal'}" for c in CASES])
def test_judge(ref, sfen, usi, expected):
    assert reference_is_legal(sfen, usi) == (expected is None), "テストの期待が基準のライブラリと合わない"
    j = ref.judge(sfen, usi)
    assert j.legal == (expected is None)
    if expected:
        assert expected in [v.rule for v in j.violations], j.as_dict()
        assert all(v.reason for v in j.violations)


def test_legal_moves_initial(ref):
    assert len(ref.legal_moves(parse_sfen(INITIAL))) == 30


def test_checkmate(ref):
    mate = "4k4/4G4/4P4/9/9/9/9/9/4K4 w - 1"
    assert shogi.Board(mate).is_checkmate()
    assert ref.is_checkmate(parse_sfen(mate))
    assert not ref.is_checkmate(parse_sfen(INITIAL))


def test_judgement_json(ref):
    d = ref.judge("lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b P 1", "P*5e").as_dict()
    assert d["legal"] is False and d["violations"][0]["rule"] == "R-NIFU"
    assert "5筋に先手の歩（5七）" in d["violations"][0]["reason"]
    assert d["legal_move_count"] > 0 and d["legal_move_examples"]
