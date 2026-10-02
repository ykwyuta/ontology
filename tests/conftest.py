from datetime import date
from pathlib import Path

import pytest

from legal_onto import lawxml
from legal_onto.egov import Revision

FIXTURES = Path(__file__).parent / "fixtures"
LAW = "501AC0000000999"


def snapshot(name: str) -> lawxml.Snapshot:
    return lawxml.parse((FIXTURES / name).read_text(encoding="utf-8"), LAW)


@pytest.fixture
def v1() -> lawxml.Snapshot:
    return snapshot("mini_v1.xml")


@pytest.fixture
def v2() -> lawxml.Snapshot:
    return snapshot("mini_v2.xml")


@pytest.fixture
def revisions() -> list[Revision]:
    return [
        Revision(f"{LAW}_20190101_000", "試験法", date(2019, 1, 1), "PreviousEnforced", None),
        Revision(f"{LAW}_20200401_001", "試験法", date(2020, 4, 1), "CurrentEnforced", None),
    ]
