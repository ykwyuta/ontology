"""規範をコンパイルして、tests/cases/*.yaml の事案が期待どおりの結論になるか（TypeDB が必要）。"""
from pathlib import Path

import pytest

from legal_onto import cases, compiler, db, norms

pytestmark = pytest.mark.typedb
TEST_DB = "legal-test-norms"
CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))


@pytest.fixture(scope="module")
def env():
    try:
        with db.connect() as d:
            d.databases.all()
            ns = norms.load_dir()
            db.init_database(d, TEST_DB, recreate=True)
            norms.store(d, ns, TEST_DB, link_sources=False)   # 条文層なし
            compiler.install(d, ns, TEST_DB)
            yield d, ns
            d.databases.get(TEST_DB).delete()
    except Exception as e:  # noqa: BLE001
        if "connect" in str(e).lower():
            pytest.skip(f"TypeDB に接続できない: {e}")
        raise


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(env, path):
    driver, ns = env
    case = cases.parse_case(path)
    cases.store_case(driver, case, TEST_DB)
    results = cases.evaluate(driver, case, ns, TEST_DB)
    wrong = [(r.claim.id, r.claim.expect, r.outcome) for r in results if r.claim.expect and r.claim.expect != r.outcome]
    assert not wrong, wrong


def test_report_lists_missing_fact_with_burden(env):
    driver, ns = env
    case = cases.parse_case(Path(__file__).parent / "cases" / "demo-001.yaml")
    cases.store_case(driver, case, TEST_DB)
    [r] = cases.evaluate(driver, case, ns, TEST_DB)
    text = cases.report(r, ns)
    assert "請求される側: 請求する側が、錯誤を知り、又は重大な過失によって知らなかったこと［真偽不明］" in text
    assert "D96-fraud" not in text            # 共通の事実（取消しの意思表示）だけでは争点にしない
    assert "unreviewed" in text


def test_sources_match_provision_layer():
    """norms/*.yaml の根拠条文の文言が、条文層（legal データベースの民法）と一致する。"""
    with db.connect() as d:
        if not d.databases.contains(db.DATABASE) or not norms.provision_layer_loaded(d):
            pytest.skip("legal データベースに民法が取り込まれていない")
        assert norms.check_sources(d, norms.load_dir()) == []
