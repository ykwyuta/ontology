from conftest import LAW


def test_structure(v1):
    p = v1.provisions
    assert p[f"{LAW}/ch1"].grouping_kind == "chapter"
    assert p[f"{LAW}/a1"].parent == f"{LAW}/ch1"
    assert p[f"{LAW}/a1"].caption == "（錯誤）"
    s = p[f"{LAW}/a1/p1"].sentences
    assert [x.function for x in s] == ["main", "proviso"]
    assert p[f"{LAW}/a2/p1/i2"].kind == "item"
    assert v1.articles_by_scope[LAW] == [f"{LAW}/a1", f"{LAW}/a2", f"{LAW}/a2_2"]
    sp = f"{LAW}/sp:令和二年法律第一号"
    assert p[sp].grouping_kind == "suppl-provision"
    assert f"{sp}/a2/p1" in p
