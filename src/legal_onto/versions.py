"""複数の版（スナップショット）を突き合わせ、規定の文言と参照に有効期間をつける。

各スナップショットはその施行日から次のスナップショットの施行日の前日まで有効とみなす。
内容が変わらない連続した版は 1 つの期間にまとめる。期間の終わり（valid-to）は「この日から無効」の意味で、
その日を含まない。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .egov import Revision
from .lawxml import Provision, Sentence, Snapshot
from .refs import Reference, extract_all


@dataclass(frozen=True)
class Period:
    valid_from: date
    valid_to: date | None
    exact_from: bool          # false: 取り込んだ最古の版から始まる（実際の施行はもっと前かもしれない）
    revision_id: str          # この期間の最初の版


@dataclass
class VersionedProvision:
    latest: Provision         # 構造・見出しは最新の版のものを使う
    texts: list[tuple[Period, tuple[Sentence, ...]]]


@dataclass
class VersionedLaw:
    law_id: str
    law_title: str
    law_num: str
    latest_revision_id: str
    provisions: dict[str, VersionedProvision]
    references: list[tuple[Period, Reference]]


def _runs(dates: list[date], revs: list[str], values: list) -> list[tuple[Period, object]]:
    """values[i] は版 i での値（None は存在しない）。同じ値が続く区間をまとめる。"""
    out = []
    i = 0
    while i < len(values):
        if values[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        end = dates[j + 1] if j + 1 < len(dates) else None
        out.append((Period(dates[i], end, i > 0, revs[i]), values[i]))
        i = j + 1
    return out


def merge(snapshots: list[tuple[Revision, Snapshot]]) -> VersionedLaw:
    if not snapshots:
        raise ValueError("no snapshots")
    dates = [r.enforcement_date for r, _ in snapshots]
    revs = [r.law_revision_id for r, _ in snapshots]
    snaps = [s for _, s in snapshots]
    latest = snaps[-1]

    paths: dict[str, None] = {}
    for s in snaps:
        paths.update(dict.fromkeys(s.provisions))

    provisions: dict[str, VersionedProvision] = {}
    for path in paths:
        latest_p = next(s.provisions[path] for s in reversed(snaps) if path in s.provisions)
        values = [s.provisions[path].sentences if path in s.provisions else None for s in snaps]
        texts = [(p, v) for p, v in _runs(dates, revs, values) if v]
        provisions[path] = VersionedProvision(latest_p, texts)

    per_snap = []
    for s in snaps:
        d = {}
        for r in extract_all(s):
            d.setdefault((r.citing, r.cited, r.kind), r)
        per_snap.append(d)
    keys: dict[tuple, None] = {}
    for d in per_snap:
        keys.update(dict.fromkeys(d))
    references = []
    for k in keys:
        values = [k if k in d else None for d in per_snap]
        for period, _ in _runs(dates, revs, values):
            # 参照文字列は期間の最初の版のもの
            idx = dates.index(period.valid_from)
            references.append((period, per_snap[idx][k]))

    return VersionedLaw(latest.law_id, latest.law_title, latest.law_num, revs[-1], provisions, references)
