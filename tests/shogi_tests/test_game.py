"""対局の審判（TypeDB が必要）。"""
import pytest

from legal_onto import db
from shogi_referee.game import Game
from shogi_referee.referee import Referee

pytestmark = pytest.mark.typedb
TEST_DB = "shogi-test-game"
KINGS_ONLY = "4k4/9/9/9/9/9/9/9/4K4 b - 1"


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


def play_all(g: Game, moves: list[str]) -> Game:
    for m in moves:
        if g.over:
            break
        g.play(m)
    return g


def test_strict_illegal_loses(ref):
    g = play_all(Game(ref), ["7g7e"])
    assert g.result.winner == "gote" and g.result.reason == "illegal" and "R-MOVE" in g.result.detail


def test_retry_allows_correction(ref):
    g = play_all(Game(ref, mode="retry"), ["7g7e", "7g7f"])
    assert not g.over and g.moves == ["7g7f"]
    assert [a.judgement.legal for a in g.attempts] == [False, True]


def test_retry_limit(ref):
    g = play_all(Game(ref, mode="retry", max_retries=1), ["7g7e", "5e5d"])
    assert g.result.reason == "illegal" and g.result.winner == "gote"


def test_checkmate(ref):
    g = play_all(Game(ref, start="4k4/9/4P4/9/9/9/9/9/4K4 b G 1"), ["G*5b"])
    assert g.result.winner == "sente" and g.result.reason == "checkmate"


def test_repetition_draw(ref):
    g = play_all(Game(ref, start=KINGS_ONLY), ["5i4i", "5a4a", "4i5i", "4a5a"] * 3)
    assert g.result.reason == "repetition" and g.result.winner is None
    assert len(g.moves) == 12


def test_perpetual_check_loses(ref):
    # 先手の飛車が王手をかけ続け、後手玉が 5一 と 5二 を往復する
    g = play_all(Game(ref, start="R3k4/9/9/9/9/9/9/9/8K w - 1"), ["5a5b", "9a9b", "5b5a", "9b9a"] * 3)
    assert g.result.reason == "perpetual-check" and g.result.winner == "gote"


def test_max_moves(ref):
    g = play_all(Game(ref, start=KINGS_ONLY, max_moves=2), ["5i4i", "5a4a"])
    assert g.result.reason == "max-moves"


def test_resign(ref):
    g = play_all(Game(ref), ["resign"])
    assert g.result.winner == "gote" and g.result.reason == "resign"
