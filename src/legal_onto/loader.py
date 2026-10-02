"""版つきの法令（VersionedLaw）を TypeDB の条文層に書き込む。

規定は親から順にまとめて insert し、返ってきた IID で後続の親子関係と参照を結ぶ。
provision-path で既存の規定を照合すると 1 件あたり約 10ms かかるのに対し、IID による照合は約 1ms で済む。
また 1 つのクエリの変数は 65535 個までなので、法令全体を 1 つのクエリにはできない。
"""
from __future__ import annotations

import time
from datetime import date

from typedb.driver import Driver, TransactionType

from .db import DATABASE
from .versions import Period, VersionedLaw, VersionedProvision

LAW_TYPE = {"Act": "act", "CabinetOrder": "cabinet-order", "MinisterialOrdinance": "ministerial-ordinance",
            "Constitution": "constitution", "Rule": "rule"}
CHUNK = 300   # 1 つの insert に入れる規定の数


def q(s: str) -> str:
    """TypeQL の文字列リテラル。"""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def d(v: date) -> str:
    return v.isoformat()


def _period(p: Period) -> str:
    s = f", has valid-from {d(p.valid_from)}, has valid-from-exact {str(p.exact_from).lower()}"
    if p.valid_to is not None:
        s += f", has valid-to {d(p.valid_to)}"
    return s


def delete_law(driver: Driver, law_id: str, database: str = DATABASE) -> None:
    """法令と、その規定・文言を削除する（役割を失った包含・参照の関係は TypeDB が消す）。"""
    with driver.transaction(database, TransactionType.WRITE) as tx:
        tx.query(f"""
            match $p isa provision, has provision-path $path; $path like "^{law_id}/";
                  provision-version (provision: $p, version: $v);
            delete $v;""").resolve()
        tx.query(f"""
            match $p isa provision, has provision-path $path; $path like "^{law_id}/";
            delete $p;""").resolve()
        tx.query(f"match $l isa law, has law-id {q(law_id)}; delete $l;").resolve()
        tx.commit()


def _provision_statements(vp: VersionedProvision, var: str, parent: str, n: int) -> tuple[list[str], int]:
    """規定・親との包含・文言の版の insert 文。n は文言の変数の通し番号。"""
    p = vp.latest
    s = f"{var} isa {p.kind}, has provision-path {q(p.path)}"
    if p.num is not None:
        s += f", has provision-num {q(p.num)}"
    if p.caption:
        s += f", has caption {q(p.caption)}"
    if p.grouping_kind:
        s += f", has grouping-kind {q(p.grouping_kind)}"
    out = [s + ";", f"containment (container: {parent}, part: {var});"]
    for period, sentences in vp.texts:
        for sen in sentences:
            t = (f"$v{n} isa text-version, has body-text {q(sen.text)}, has sentence-num {sen.num}"
                 f"{_period(period)}, has law-revision-id {q(period.revision_id)}")
            if sen.function:
                t += f", has sentence-function {q(sen.function)}"
            out.append(t + f"; provision-version (provision: {var}, version: $v{n});")
            n += 1
    return out, n


def _depth(law: VersionedLaw, path: str) -> int:
    n, parent = 0, law.provisions[path].latest.parent
    while parent is not None:
        n, parent = n + 1, law.provisions[parent].latest.parent
    return n


def _one_row(tx, query: str):
    rows = list(tx.query(query).resolve().as_concept_rows())
    if len(rows) != 1:
        raise RuntimeError(f"expected 1 row, got {len(rows)}:\n{query[:1500]}")
    return rows[0]


def load(driver: Driver, law: VersionedLaw, law_type: str, database: str = DATABASE) -> dict[str, int]:
    t0 = time.time()
    provs = sorted(law.provisions.values(), key=lambda vp: _depth(law, vp.latest.path))  # 親を子より先に
    iid: dict[str, str] = {}
    n_versions = 0
    with driver.transaction(database, TransactionType.WRITE) as tx:
        law_iid = _one_row(tx, (
            f"insert $law isa law, has law-id {q(law.law_id)}, has law-title {q(law.law_title)}, "
            f"has law-num {q(law.law_num)}, has law-type {q(LAW_TYPE.get(law_type, 'act'))}, "
            f"has law-revision-id {q(law.latest_revision_id)};")).get("law").get_iid()

        for start in range(0, len(provs), CHUNK):
            chunk = provs[start:start + CHUNK]
            local = {vp.latest.path: f"$p{i}" for i, vp in enumerate(chunk)}
            outer: dict[str, str] = {}      # このクエリの外で作った親: 変数 -> IID
            outer_var: dict[str, str] = {}  # 親のパス -> 変数
            body: list[str] = []
            for vp in chunk:
                parent_path = vp.latest.parent
                if parent_path is None:
                    outer["$law"] = law_iid
                    parent = "$law"
                elif parent_path in local:
                    parent = local[parent_path]
                else:
                    if parent_path not in outer_var:
                        outer_var[parent_path] = f"$o{len(outer_var)}"
                        outer[outer_var[parent_path]] = iid[parent_path]
                    parent = outer_var[parent_path]
                stmts, n_versions = _provision_statements(vp, local[vp.latest.path], parent, n_versions)
                body.extend(stmts)
            # IID だけで照合した変数は型が推論されないため isa を添える（TypeDB 3.13 で確認）
            match = ("match " + " ".join(
                f"{k} iid {v}; {k} isa {'law' if k == '$law' else 'provision'};" for k, v in outer.items()
            ) + "\n") if outer else ""
            row = _one_row(tx, match + "insert\n" + "\n".join(body))
            for path, var in local.items():
                iid[path] = row.get(var[1:]).get_iid()
        print(f"    provisions and text versions: {time.time() - t0:.1f}s", flush=True)

        t1 = time.time()
        for period, r in law.references:
            _one_row(tx, (
                f"match $a iid {iid[r.citing]}; $a isa provision; $b iid {iid[r.cited]}; $b isa provision;\n"
                f"insert cross-reference (citing: $a, cited: $b), has reference-kind {q(r.kind)}, "
                f"has reference-text {q(r.text)}{_period(period)};"))
        print(f"    references: {time.time() - t1:.1f}s", flush=True)
        tx.commit()
    return {"provisions": len(provs), "text_versions": n_versions, "references": len(law.references)}
