"""TypeDB サーバ（docker compose up -d）を使うテスト。サーバに接続できなければスキップする。"""
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import LAW

from legal_onto import db, loader
from legal_onto.versions import merge

pytestmark = pytest.mark.typedb
TEST_DB = "legal-test"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def driver():
    try:
        with db.connect() as d:
            d.databases.all()
            yield d
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"TypeDB に接続できない: {e}")


@pytest.fixture(scope="module")
def loaded(driver, request):
    from conftest import snapshot
    from legal_onto.egov import Revision
    from datetime import date
    revs = [Revision(f"{LAW}_20190101_000", "試験法", date(2019, 1, 1), "PreviousEnforced", None),
            Revision(f"{LAW}_20200401_001", "試験法", date(2020, 4, 1), "CurrentEnforced", None)]
    db.init_database(driver, TEST_DB, recreate=True)
    law = merge([(revs[0], snapshot("mini_v1.xml")), (revs[1], snapshot("mini_v2.xml"))])
    loader.load(driver, law, "Act", TEST_DB)
    yield driver
    driver.databases.get(TEST_DB).delete()


def values(driver, query, key):
    return sorted(r[key] for r in db.rows(driver, query, TEST_DB))


def text_at(driver, path, at):
    return values(driver, f"""
        match $p isa provision, has provision-path "{LAW}/{path}";
              let $v in text_at($p, {at}); $v has body-text $t;
        fetch {{ "t": $t }};""", "t")


def test_text_at(loaded):
    assert text_at(loaded, "a1/p1", "2019-06-01") == sorted([
        "意思表示は、法律行為の要素に錯誤があったときは、無効とする。",
        "ただし、表意者に重大な過失があったときは、表意者は、自らその無効を主張することができない。"])
    assert text_at(loaded, "a1/p1", "2020-04-01") == [
        "意思表示は、錯誤に基づくものであって、その錯誤が重要なものであるときは、取り消すことができる。"]
    assert text_at(loaded, "a2/p2", "2020-04-01") == []   # 削除された項


def test_containment_and_law(loaded):
    assert values(loaded, f"""
        match $l isa law, has law-id "{LAW}"; containment (container: $l, part: $g);
              $g has provision-path $p; fetch {{ "p": $p }};""", "p") == [
        f"{LAW}/ch1", f"{LAW}/sp:令和二年法律第一号"]


def test_references_by_date(loaded):
    def citing_at(path, at):
        return values(loaded, f"""
            match $p isa provision, has provision-path "{LAW}/{path}";
                  let $q in citing_at($p, {at}); $q has provision-path $x;
            fetch {{ "x": $x }};""", "x")
    sp = f"{LAW}/sp:令和二年法律第一号"
    # 2条1項を（推移的に）参照する規定: 2019 年は 2条2項と、それを参照する 附則2条・2条の2
    assert citing_at("a2/p1", "2019-06-01") == sorted([f"{LAW}/a2/p2", f"{sp}/a2/p1", f"{LAW}/a2_2/p1"])
    # 2020 年には 2条2項が削除されている
    assert citing_at("a2/p1", "2020-04-01") == []


def test_transitive_references(loaded):
    assert values(loaded, f"""
        match $p isa provision, has provision-path "{LAW}/a2_2/p1";
              let $q in referenced_transitively($p); $q has provision-path $x;
        fetch {{ "x": $x }};""", "x") == sorted([
        f"{LAW}/a1", f"{LAW}/a2", f"{LAW}/a2/p2", f"{LAW}/a2/p1", f"{LAW}/a2/p1/i1"])


def test_proposal_typeql(driver):
    """提案書 04 の TypeQL と例題の検証スクリプトが通る。"""
    r = subprocess.run([sys.executable, str(ROOT / "scripts/verify_proposal_typeql.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
