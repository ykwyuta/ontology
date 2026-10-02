from datetime import date

from conftest import LAW

from legal_onto.versions import merge


def test_merge(v1, v2, revisions):
    law = merge([(revisions[0], v1), (revisions[1], v2)])
    a1 = law.provisions[f"{LAW}/a1/p1"].texts
    assert len(a1) == 2
    (p_old, s_old), (p_new, s_new) = a1
    assert (p_old.valid_from, p_old.valid_to, p_old.exact_from) == (date(2019, 1, 1), date(2020, 4, 1), False)
    assert (p_new.valid_from, p_new.valid_to, p_new.exact_from) == (date(2020, 4, 1), None, True)
    assert "無効" in s_old[0].text and "取り消す" in s_new[0].text

    # 変わらない規定は 1 つの期間にまとまる
    assert [p.valid_to for p, _ in law.provisions[f"{LAW}/a2/p1"].texts] == [None]
    # 削除された項は v1 の期間だけ
    assert [p.valid_to for p, _ in law.provisions[f"{LAW}/a2/p2"].texts] == [date(2020, 4, 1)]

    # 削除された項からの参照も、その期間だけ有効
    refs = {(r.citing, r.cited): p for p, r in law.references}
    p = refs[(f"{LAW}/a2/p2", f"{LAW}/a2/p1")]
    assert p.valid_to == date(2020, 4, 1)
    # 附則の「新法第二条第二項」は参照先が v2 で消えるので v1 だけ
    sp = f"{LAW}/sp:令和二年法律第一号"
    assert refs[(f"{sp}/a2/p1", f"{LAW}/a2/p2")].valid_to == date(2020, 4, 1)
    assert refs[(f"{sp}/a2/p1", f"{LAW}/a1")].valid_to is None
