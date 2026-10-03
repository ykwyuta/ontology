"""SFEN・USI の解析と、指し手の適用（TypeDB 不要）。"""
import pytest

from shogi_referee.sfen import INITIAL, Move, SfenError, apply_move, parse_sfen, parse_usi, to_sfen


def test_roundtrip_initial():
    pos = parse_sfen(INITIAL)
    assert pos.board[(5, 9)] == ("K", "sente") and pos.board[(2, 2)] == ("B", "gote")
    assert pos.board[(8, 8)] == ("B", "sente") and pos.board[(2, 8)] == ("R", "sente")
    assert to_sfen(pos) == INITIAL


def test_hands_and_promoted():
    s = "4k4/9/4+P4/9/9/9/9/9/4K4 w 2Pb 10"
    pos = parse_sfen(s)
    assert pos.board[(5, 3)] == ("+P", "sente")
    assert pos.hands == {"sente": {"P": 2}, "gote": {"B": 1}}
    assert to_sfen(pos) == s


def test_usi():
    assert parse_usi("7g7f") == Move(to=(7, 6), frm=(7, 7))
    assert parse_usi("8h2b+") == Move(to=(2, 2), frm=(8, 8), promote=True)
    assert parse_usi("P*5e") == Move(to=(5, 5), drop="P")
    assert parse_usi("P*5e").usi == "P*5e"
    for bad in ("7g7f7", "0a1a", "+P*5e", "K*5e", ""):
        with pytest.raises(SfenError):
            parse_usi(bad)


def test_apply_capture_unpromotes():
    pos = parse_sfen("4k4/9/9/9/4+r4/4G4/9/9/4K4 b - 1")
    after = apply_move(pos, parse_usi("5f5e"))
    assert after.hands["sente"] == {"R": 1}
    assert after.board[(5, 5)] == ("G", "sente") and after.side == "gote"
