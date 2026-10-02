"""規範の読み込み・検証・コンパイル（TypeDB 不要）。"""
import textwrap
from pathlib import Path

import pytest

from legal_onto import compiler, norms
from legal_onto.norms import NormError

GROUND = """
- id: G
  label: 請求
  effect: claim
  category: arising
  claim-type: t
  sources: [{path: a1}]
  authority: [テスト]
  when: {fact: F.g, label: 請求原因}
"""


def load(tmp_path: Path, body: str) -> dict:
    (tmp_path / "n.yaml").write_text(textwrap.dedent(GROUND) + textwrap.dedent(body), encoding="utf-8")
    return norms.load_dir(tmp_path)


def norm(id_, exc, when="{fact: F.x, label: x}", extra=""):
    return f"""
- id: {id_}
  label: {id_}
  effect: e
  category: impeding
  exception-of: [{exc}]
  sources: [{{path: a1}}]
  authority: [テスト]
  when: {when}
{extra}"""


def test_repository_norms_are_valid():
    ns = norms.load_dir()
    assert len(ns) >= 20
    assert ns["G555-price"].layer == 0
    assert ns["D95"].layer == 1 and ns["D95"].burden == "respondent"
    assert ns["R95-3"].layer == 2 and ns["R95-3"].burden == "claimant"
    assert ns["E95-3"].layer == 3 and ns["E95-3"].burden == "respondent"
    assert ns["NR95"].layer == 1    # 抗弁の要件として使う部品は、抗弁と同じ層


def test_layers(tmp_path):
    ns = load(tmp_path, norm("D", "G") + norm("R", "D", "{fact: F.r, label: r}"))
    assert (ns["D"].layer, ns["R"].layer) == (1, 2)


def test_cycle_is_rejected(tmp_path):
    with pytest.raises(NormError, match="循環"):
        load(tmp_path, norm("D", "G") + norm("R", "D", "{fact: F.r, label: r}")
             + norm("S", "R", "{norm: D}"))


def test_parity_conflict_is_rejected(tmp_path):
    # E は D（層1）と R（層2）の両方の例外になっていて、証明責任が決まらない
    with pytest.raises(NormError, match="偶奇"):
        load(tmp_path, norm("D", "G") + norm("R", "D", "{fact: F.r, label: r}")
             + norm("E", "D, R", "{fact: F.e, label: e}"))


def test_authority_is_required(tmp_path):
    body = norm("D", "G").replace("  authority: [テスト]\n", "")
    with pytest.raises(NormError, match="典拠"):
        load(tmp_path, body)


def test_fact_label_must_match(tmp_path):
    with pytest.raises(NormError, match="label"):
        load(tmp_path, norm("D", "G", "{fact: F.g, label: 違う説明}"))


def test_valid_from_needs_anchor(tmp_path):
    with pytest.raises(NormError, match="time-anchor"):
        load(tmp_path, norm("D", "G", extra="  valid-from: 2020-04-01"))


def test_compiled_functions():
    ns = norms.load_dir()
    query, names = compiler.compile_norms(ns)
    assert len(names) == 2 * len(ns) + len(compiler.OUTCOME_FUNCTIONS)
    # 抗弁は請求原因の h_ で否定され、阻止の抗弁（同時履行）は否定されない
    h_g = query[query.index("fun h_g555_price("):]
    h_g = h_g[:h_g.index("return")]
    assert "in h_d473($c); };" in h_g and "not { let $z" in h_g
    assert "h_d533" not in h_g
    # 適用期間は時点で判定する
    c_r95 = query[query.index("fun c_r95_3("):]
    assert '$tp isa time-point, links (subject: $c), has anchor-code "declaration", has at $t; $t >= 2020-04-01;' in c_r95
