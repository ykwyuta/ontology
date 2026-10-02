from conftest import LAW

from legal_onto.refs import Resolver, mask_quotes


def refs_of(snap, path):
    return {(r.cited.removeprefix(LAW + "/"), r.kind) for r in Resolver(snap).extract(snap.provisions[f"{LAW}/{path}"])}


def test_relative_article(v1):
    assert refs_of(v1, "a2/p1") == {("a1", "refer")}


def test_item_relative_and_external_law(v1):
    # 「民事執行法第百六十七条」は他の法令なので除く
    assert refs_of(v1, "a2/p1/i2") == {("a2/p1/i1", "refer")}


def test_notwithstanding_and_same_paragraph(v1):
    assert refs_of(v1, "a2/p2") == {
        ("a2/p1", "notwithstanding"), ("a1", "refer"), ("a2/p1/i1", "refer")}


def test_range_apply_and_read_as_ignoring_quotes(v1):
    assert refs_of(v1, "a2_2/p1") == {
        ("a1", "apply-mutatis-mutandis"), ("a2", "apply-mutatis-mutandis"),
        ("a2/p2", "read-as")}  # かぎ括弧の中の「前項」「第三条」は参照ではない


def test_suppl_provision_scopes(v1):
    sp = "sp:令和二年法律第一号"
    # 前置きのない「第二条」は改正法の本則なので除き、「附則第二条」は同じ附則の中
    assert refs_of(v1, f"{sp}/a1/p1") == {(f"{sp}/a2", "refer")}
    # 「新法第一条、第二条第二項及び第二条の二」は本則。列挙の後ろにも「新法」が及ぶ
    assert refs_of(v1, f"{sp}/a2/p1") == {
        ("a1", "notwithstanding"), ("a2/p2", "notwithstanding"), ("a2_2", "notwithstanding")}


def test_mask_quotes():
    assert mask_quotes("中「前項」とある") == "中「＿＿」とある"


def _snap_with(v1, text):
    """v1 の 2条の2 第1項の文言を差し替えたスナップショット。"""
    import copy
    from legal_onto.lawxml import Sentence
    snap = copy.deepcopy(v1)
    snap.provisions[f"{LAW}/a2_2/p1"].sentences = (Sentence(1, None, text),)
    return snap


def test_paragraph_range_inherits_article(v1):
    snap = _snap_with(v1, "第二条第一項から第二項までの規定は、準用する。")
    assert refs_of(snap, "a2_2/p1") == {("a2/p1", "apply-mutatis-mutandis"), ("a2/p2", "apply-mutatis-mutandis")}


def test_parenthetical_inherits_article(v1):
    snap = _snap_with(v1, "前条（第二号に係る部分に限る。）の規定による。")
    assert ("a2/p1/i2", "refer") in refs_of(snap, "a2_2/p1")


def test_chain_after_other_law_is_external(v1):
    snap = _snap_with(v1, "民事執行法第百六十七条若しくは第一条の規定又は同条第二項の規定による。")
    assert refs_of(snap, "a2_2/p1") == set()


def test_kind_after_parenthetical(v1):
    snap = _snap_with(v1, "第一条から第二条まで（第二条ただし書を除く。）の規定は、前項の場合について準用する。")
    assert refs_of(snap, "a2_2/p1") == {
        ("a1", "apply-mutatis-mutandis"), ("a2", "apply-mutatis-mutandis"), ("a2", "exclude")}


def test_grouping_references(v1):
    snap = _snap_with(v1, "この章（第一条を除く。）の規定は、代理人について準用する。")
    assert refs_of(snap, "a2_2/p1") == {("ch1", "apply-mutatis-mutandis"), ("a1", "exclude")}
    snap = _snap_with(v1, "第一章の規定による。この目的のために")
    assert refs_of(snap, "a2_2/p1") == {("ch1", "refer")}
