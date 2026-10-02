"""規範（norms/*.yaml）の読み込み・検証・TypeDB への書き込み。

検証すること:
  - 書式（必須項目、値の範囲、参照先の規範の存在）
  - 例外関係と規範の参照に循環がないこと（層化否定の条件）
  - 層（請求原因 0、抗弁 1、…）の偶奇が一意に決まること（証明責任の配分のため）
  - 同じ要件事実（fact-code）の説明と規範的要件かどうかが、規範の間で一致すること
  - 根拠条文が条文層にあり、その文言に quote が含まれること（条文層が取り込み済みのとき）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from typedb.driver import Driver, TransactionType

from .db import DATABASE
from .loader import q

NORMS_DIR = Path(__file__).resolve().parents[2] / "norms"
DEFAULT_LAW = "129AC0000000089"   # 民法
REVIEW_STATUSES = {"unreviewed", "source-checked", "proleg-matched", "user-confirmed", "disputed"}
CATEGORIES = {"arising", "impeding", "extinguishing", "blocking", "auxiliary"}
TIME_ANCHORS = {"declaration", "contract", "claim-arose"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class NormError(ValueError):
    pass


@dataclass
class Cond:
    kind: str                       # "fact", "norm", "all", "any"
    code: str | None = None         # fact-code / 規範ID
    label: str | None = None
    evaluative: bool = False
    children: list[Cond] = field(default_factory=list)

    def facts(self) -> list[Cond]:
        if self.kind == "fact":
            return [self]
        return [f for c in self.children for f in c.facts()]

    def norm_refs(self) -> list[str]:
        if self.kind == "norm":
            return [self.code]
        return [r for c in self.children for r in c.norm_refs()]


@dataclass
class Norm:
    id: str
    label: str
    effect: str
    category: str
    when: Cond
    claim_type: str | None = None
    exception_of: list[str] = field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None
    time_anchor: str | None = None
    stance: str = "条文"
    sources: list[tuple[str, str | None]] = field(default_factory=list)   # (provision-path, quote)
    precedents: list[str] = field(default_factory=list)
    authority: list[str] = field(default_factory=list)
    note: str | None = None
    review_status: str = "unreviewed"
    file: str = ""
    layer: int | None = None        # 検証で計算する

    @property
    def burden(self) -> str:
        return "claimant" if (self.layer or 0) % 2 == 0 else "respondent"


def _cond(d, where: str) -> Cond:
    if not isinstance(d, dict) or len(set(d) & {"all", "any", "fact", "norm"}) != 1:
        raise NormError(f"{where}: 要件は all / any / fact / norm のどれか 1 つ: {d!r}")
    if "all" in d or "any" in d:
        kind = "all" if "all" in d else "any"
        items = d[kind]
        if not isinstance(items, list) or not items:
            raise NormError(f"{where}: {kind} には 1 つ以上の要件が必要")
        return Cond(kind, children=[_cond(x, where) for x in items])
    if "norm" in d:
        return Cond("norm", code=str(d["norm"]))
    if not d.get("label"):
        raise NormError(f"{where}: 要件事実 {d['fact']} に label がない")
    return Cond("fact", code=str(d["fact"]), label=str(d["label"]), evaluative=bool(d.get("evaluative", False)))


def _date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def _path(p: str) -> str:
    return p if re.match(r"^\d{3}[A-Z]{2}\d", p) else f"{DEFAULT_LAW}/{p}"


def parse_file(path: Path) -> list[Norm]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    out = []
    for i, d in enumerate(data):
        where = f"{path.name}[{i}]"
        for k in ("id", "label", "effect", "category", "when"):
            if k not in d:
                raise NormError(f"{where}: {k} がない")
        where = f"{path.name}:{d['id']}"
        out.append(Norm(
            id=str(d["id"]), label=str(d["label"]), effect=str(d["effect"]), category=str(d["category"]),
            when=_cond(d["when"], where),
            claim_type=d.get("claim-type"),
            exception_of=[str(x) for x in d.get("exception-of", [])],
            valid_from=_date(d.get("valid-from")), valid_to=_date(d.get("valid-to")),
            time_anchor=d.get("time-anchor"),
            stance=str(d.get("stance", "条文")),
            sources=[(_path(str(s["path"])), s.get("quote")) for s in d.get("sources", [])],
            precedents=[str(x) for x in d.get("precedents", [])],
            authority=[str(x) for x in d.get("authority", [])],
            note=d.get("note"),
            review_status=str(d.get("review-status", "unreviewed")),
            file=path.name,
        ))
    return out


def load_dir(directory: Path = NORMS_DIR) -> dict[str, Norm]:
    norms: dict[str, Norm] = {}
    for f in sorted(directory.glob("*.yaml")):
        for n in parse_file(f):
            if n.id in norms:
                raise NormError(f"規範ID {n.id} が重複（{norms[n.id].file} と {n.file}）")
            norms[n.id] = n
    validate(norms)
    return norms


def exceptions_of(norms: dict[str, Norm], base: str) -> list[Norm]:
    return [n for n in norms.values() if base in n.exception_of]


def validate(norms: dict[str, Norm]) -> None:
    for n in norms.values():
        w = f"{n.file}:{n.id}"
        if not ID_RE.match(n.id):
            raise NormError(f"{w}: 規範IDに使えない文字がある")
        if n.category not in CATEGORIES:
            raise NormError(f"{w}: category は {sorted(CATEGORIES)} のどれか")
        if n.category == "arising":
            if not n.claim_type or n.exception_of:
                raise NormError(f"{w}: 請求原因（arising）には claim-type が必要で、exception-of は持てない")
        elif n.category == "auxiliary":
            if n.exception_of:
                raise NormError(f"{w}: auxiliary は exception-of を持てない（他の規範の要件として使う）")
        elif not n.exception_of:
            raise NormError(f"{w}: 抗弁・再抗弁などには exception-of が必要")
        if (n.valid_from or n.valid_to) and n.time_anchor not in TIME_ANCHORS:
            raise NormError(f"{w}: valid-from / valid-to があるときは time-anchor（{sorted(TIME_ANCHORS)}）が必要")
        if n.review_status not in REVIEW_STATUSES:
            raise NormError(f"{w}: review-status は {sorted(REVIEW_STATUSES)} のどれか")
        if not n.authority:
            raise NormError(f"{w}: 典拠（authority）のない規範は登録しない（06-decisions.md 6.2）")
        if not n.sources and not n.precedents:
            raise NormError(f"{w}: 根拠条文（sources）か判例（precedents）が必要")
        for ref in n.exception_of + n.when.norm_refs():
            if ref not in norms:
                raise NormError(f"{w}: 規範 {ref} がない")
        for base in n.exception_of:
            if n.category == "blocking" and norms[base].category != "arising":
                raise NormError(f"{w}: 阻止（blocking）の規範は請求原因に対する抗弁としてだけ使える")
    for n in norms.values():
        if n.category == "auxiliary" and not any(n.id in m.when.norm_refs() for m in norms.values()):
            raise NormError(f"{n.file}:{n.id}: どの規範からも参照されていない auxiliary")

    _check_acyclic(norms)
    _assign_layers(norms)

    facts: dict[str, tuple[str, bool, str]] = {}
    for n in norms.values():
        for f in n.when.facts():
            prev = facts.setdefault(f.code, (f.label, f.evaluative, n.id))
            if prev[:2] != (f.label, f.evaluative):
                raise NormError(f"要件事実 {f.code} の label / evaluative が {prev[2]} と {n.id} で異なる")


def dependencies(n: Norm) -> list[str]:
    """関数 h_<n> が呼ぶ規範（例外は否定、要件中の規範は肯定）。"""
    return n.when.norm_refs()


def _check_acyclic(norms: dict[str, Norm]) -> None:
    graph = {n.id: dependencies(n) + [e.id for e in exceptions_of(norms, n.id)] for n in norms.values()}
    state: dict[str, int] = {}

    def visit(v: str, stack: list[str]) -> None:
        if state.get(v) == 2:
            return
        if state.get(v) == 1:
            raise NormError("規範の例外関係・参照が循環している（層化できない）: " + " -> ".join(stack + [v]))
        state[v] = 1
        for w in graph[v]:
            visit(w, stack + [v])
        state[v] = 2

    for v in graph:
        visit(v, [])


def _assign_layers(norms: dict[str, Norm]) -> None:
    layers: dict[str, set[int]] = {}

    def walk(n: Norm, layer: int) -> None:
        layers.setdefault(n.id, set()).add(layer)
        for ref in n.when.norm_refs():
            walk(norms[ref], layer)           # 要件として使う規範は、使う側と同じ層
        for e in exceptions_of(norms, n.id):
            walk(e, layer + 1)

    for n in norms.values():
        if n.category == "arising":
            walk(n, 0)
    for n in norms.values():
        ls = layers.get(n.id)
        if not ls:
            raise NormError(f"{n.file}:{n.id}: どの請求原因からもたどれない")
        if len({x % 2 for x in ls}) > 1:
            raise NormError(f"{n.file}:{n.id}: 層の偶奇が一意でない {sorted(ls)}（証明責任を決められない）")
        n.layer = min(ls)


# --- 条文層との照合 ---

def check_sources(driver: Driver, norms: dict[str, Norm], database: str = DATABASE) -> list[str]:
    """根拠条文の存在と文言の照合。問題の一覧を返す（空なら問題なし）。"""
    problems = []
    with driver.transaction(database, TransactionType.READ) as tx:
        for n in norms.values():
            at = n.valid_from or date.today()
            for path, quote in n.sources:
                rows = list(tx.query(f"""
                    match $r isa provision, has provision-path {q(path)};
                          {{ $p is $r; }} or {{ let $p in parts_transitively($r); }};
                          let $v in text_at($p, {at.isoformat()}); $v has body-text $t;
                    select $t;""").resolve().as_concept_rows())
                if not rows:
                    problems.append(f"{n.id}: {path} が条文層にない（{at} 時点）")
                    continue
                text = "".join(r.get("t").get_value() for r in rows)
                if quote and quote not in text:
                    problems.append(f"{n.id}: {path} の {at} 時点の文言に「{quote}」がない")
    return problems


def provision_layer_loaded(driver: Driver, law_id: str = DEFAULT_LAW, database: str = DATABASE) -> bool:
    with driver.transaction(database, TransactionType.READ) as tx:
        return bool(list(tx.query(f"match $l isa law, has law-id {q(law_id)};").resolve().as_concept_rows()))


# --- TypeDB への書き込み ---

def _cond_insert(c: Cond, var: str, n: Norm, out: list[str], counter: list[int], refvars: dict[str, str]) -> None:
    if c.kind == "fact":
        out.append(f"{var} isa atomic-condition, has fact-code {q(c.code)}, has fact-label {q(c.label)}, "
                   f"has evaluative {str(c.evaluative).lower()}, has burden-side {q(n.burden)};")
    elif c.kind == "norm":
        out.append(f"{var} isa norm-reference-condition; condition-norm (condition: {var}, norm: {refvars[c.code]});")
    else:
        out.append(f"{var} isa compound-condition, has connective {q('and' if c.kind == 'all' else 'or')};")
        for child in c.children:
            counter[0] += 1
            cv = f"$k{counter[0]}"
            _cond_insert(child, cv, n, out, counter, refvars)
            out.append(f"condition-part (whole: {var}, part: {cv});")


def _dependency_order(norms: dict[str, Norm]) -> list[Norm]:
    """要件として参照される規範を先に（循環がないことは validate で確認済み）。"""
    done: dict[str, Norm] = {}

    def visit(n: Norm) -> None:
        if n.id not in done:
            for r in n.when.norm_refs():
                visit(norms[r])
            done[n.id] = n

    for n in norms.values():
        visit(n)
    return list(done.values())


def delete_all(driver: Driver, database: str = DATABASE) -> None:
    with driver.transaction(database, TransactionType.WRITE) as tx:
        for t in ("condition", "norm", "precedent"):
            tx.query(f"match $x isa {t}; delete $x;").resolve()
        tx.commit()


def store(driver: Driver, norms: dict[str, Norm], database: str = DATABASE, *,
          link_sources: bool = True) -> None:
    """規範層を入れ替える。link_sources=False なら根拠条文との関係を張らない（条文層がないテスト用）。"""
    from .compiler import function_names
    delete_all(driver, database)
    with driver.transaction(database, TransactionType.WRITE) as tx:
        for n in _dependency_order(norms):
            attrs = [f"has norm-id {q(n.id)}", f"has norm-label {q(n.label)}", f"has effect-code {q(n.effect)}",
                     f"has effect-category {q(n.category)}", f"has pleading-layer {n.layer}",
                     f"has stance {q(n.stance)}", f"has review-status {q(n.review_status)}",
                     f"has function-name {q(function_names(n)['holds'])}"]
            if n.claim_type:
                attrs.append(f"has claim-type {q(n.claim_type)}")
            if n.valid_from:
                attrs.append(f"has valid-from {n.valid_from.isoformat()}")
            if n.valid_to:
                attrs.append(f"has valid-to {n.valid_to.isoformat()}")
            if n.time_anchor:
                attrs.append(f"has time-anchor {q(n.time_anchor)}")
            for a in n.authority:
                attrs.append(f"has authority-ref {q(a)}")
            if n.note:
                attrs.append(f"has review-note {q(n.note)}")
            refvars = {r: f"$m{i}" for i, r in enumerate(dict.fromkeys(n.when.norm_refs()))}
            match = " ".join(f"{v} isa norm, has norm-id {q(r)};" for r, v in refvars.items())
            out = [f"$n isa norm, {', '.join(attrs)};"]
            _cond_insert(n.when, "$k0", n, out, [0], refvars)
            out.append("norm-condition (norm: $n, root: $k0);")
            tx.query((f"match {match}\n" if match else "") + "insert " + "\n".join(out)).resolve()
            for p in n.precedents:
                tx.query(f"""
                    match $n isa norm, has norm-id {q(n.id)};
                    insert $p isa precedent, has case-number {q(p)}; norm-source (norm: $n, source: $p);""").resolve()

        for n in norms.values():
            for base in n.exception_of:
                tx.query(f"""
                    match $b isa norm, has norm-id {q(base)}; $e isa norm, has norm-id {q(n.id)};
                    insert exception (base: $b, exception: $e);""").resolve()
            if link_sources:
                for path, quote in n.sources:
                    has_quote = f", has source-quote {q(quote)}" if quote else ""
                    rows = list(tx.query(f"""
                        match $n isa norm, has norm-id {q(n.id)}; $p isa provision, has provision-path {q(path)};
                        insert $r isa norm-source (norm: $n, source: $p){has_quote};""").resolve().as_concept_rows())
                    if len(rows) != 1:
                        raise NormError(f"{n.id}: 根拠条文 {path} が条文層にない")
        tx.commit()
