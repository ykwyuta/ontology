import pytest

from legal_onto.kanji import kanji_num_path, kanji_to_int


@pytest.mark.parametrize("s,n", [("一", 1), ("十", 10), ("十五", 15), ("九十五", 95), ("百", 100),
                                 ("百二十一", 121), ("千四十四", 1044), ("千五十", 1050), ("二〇", 20)])
def test_kanji_to_int(s, n):
    assert kanji_to_int(s) == n


def test_kanji_num_path():
    assert kanji_num_path("九十八の二") == "98_2"
    assert kanji_num_path("三百九十八の二十二") == "398_22"
