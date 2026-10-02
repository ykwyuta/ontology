"""e-Gov 法令API v2 のクライアント（ローカルキャッシュつき）。"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

API = "https://laws.e-gov.go.jp/api/2"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "egov"


@dataclass(frozen=True)
class Revision:
    law_revision_id: str
    law_title: str
    enforcement_date: date | None
    status: str           # "CurrentEnforced", "PreviousEnforced", "UnEnforced" など
    amendment_law_title: str | None

    @property
    def enforced(self) -> bool:
        return self.status in ("CurrentEnforced", "PreviousEnforced")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError


def law_revisions(law_id: str) -> tuple[dict, list[Revision]]:
    """改正履歴。API は新しい順に返す。"""
    data = json.loads(_get(f"{API}/law_revisions/{urllib.parse.quote(law_id)}"))
    revs = [
        Revision(
            law_revision_id=r["law_revision_id"],
            law_title=r["law_title"],
            enforcement_date=date.fromisoformat(r["amendment_enforcement_date"])
            if r.get("amendment_enforcement_date") else None,
            status=r["current_revision_status"],
            amendment_law_title=r.get("amendment_law_title"),
        )
        for r in data["revisions"]
    ]
    return data["law_info"], revs


def snapshots(revisions: list[Revision], *, include_scheduled: bool = False) -> list[Revision]:
    """施行日ごとに 1 つの版を選び、古い順に並べる。

    同じ施行日に複数の改正がある場合、API が先に返す（新しい）版がそれらをすべて溶け込ませた版になる
    （asof 指定で取得したときに返る版と一致する）。
    """
    chosen: dict[date, Revision] = {}
    for r in revisions:
        if r.enforcement_date is None or (not r.enforced and not include_scheduled):
            continue
        chosen.setdefault(r.enforcement_date, r)
    return [chosen[d] for d in sorted(chosen)]


def law_xml(law_revision_id: str) -> str:
    """法令標準XML（改正履歴IDで指定）。取得結果はキャッシュする。"""
    path = CACHE_DIR / f"{law_revision_id}.xml"
    if path.exists():
        return path.read_text(encoding="utf-8")
    data = json.loads(_get(f"{API}/law_data/{urllib.parse.quote(law_revision_id)}?law_full_text_format=xml"))
    xml = base64.b64decode(data["law_full_text"]).decode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    time.sleep(0.5)  # API への負荷を抑える
    return xml
