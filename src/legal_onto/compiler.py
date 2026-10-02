"""規範層から TypeQL の関数を生成する（docs/proposal/04-schema-design.md 4.4、4.7）。

規範 N ごとに 2 つの関数を作る。どちらも訴訟物 $c を引数にとり、条件を満たせば $c を返す。
  c_N  要件を満たす: 要件の木（and → 連結、or → or 節、他の規範 → その h_ 関数）と、適用期間の条件
  h_N  成立する: c_N を満たし、N に対する例外（抗弁に対する再抗弁など）がどれも成立しない
        （請求原因に対する阻止の抗弁（同時履行など）は、ここでは否定せず結論の関数で扱う）
結論の関数:
  ground_holds              請求原因が成立し、消滅・障害の抗弁が成立しない
  blocked                   阻止の抗弁が成立する
  claim_granted             請求を認める
  claim_granted_in_exchange 引換給付で認める
h_N は自分より深い層の関数だけを否定の中で呼ぶ。例外関係と規範の参照に循環がないことは norms.validate で確認済みなので、
層化否定の条件を満たす。

引数をとらない関数（提案書 4.4 の形）にすると、否定の中で呼ぶたびに全訴訟物について評価し直すため、
訴訟物の数 × 否定の数に比例して遅くなる（49 件の事案で 8 分以上かかった）。
"""
from __future__ import annotations

from datetime import date

from typedb.driver import Driver, TransactionType

from .db import DATABASE
from .loader import q
from .norms import Cond, Norm, exceptions_of

OUTCOME_FUNCTIONS = ["ground_holds", "blocked", "claim_granted", "claim_granted_in_exchange"]


def _ident(norm_id: str) -> str:
    return norm_id.lower().replace("-", "_")


def function_names(n: Norm) -> dict[str, str]:
    return {"conds": f"c_{_ident(n.id)}", "holds": f"h_{_ident(n.id)}"}


def _cond_pattern(c: Cond, counter: list[int]) -> str:
    counter[0] += 1
    i = counter[0]
    if c.kind == "fact":
        return f"$f{i} isa fact-finding, links (subject: $c), has fact-code {q(c.code)}; let $f{i} in established();"
    if c.kind == "norm":
        return f"let $r{i} in h_{_ident(c.code)}($c);"
    parts = [_cond_pattern(x, counter) for x in c.children]
    if c.kind == "all":
        return " ".join(parts)
    return " or ".join("{ " + p + " }" for p in parts) + ";"


def _time_pattern(n: Norm) -> str:
    if not (n.valid_from or n.valid_to):
        return ""
    s = f"$tp isa time-point, links (subject: $c), has anchor-code {q(n.time_anchor)}, has at $t;"
    if n.valid_from:
        s += f" $t >= {n.valid_from.isoformat()};"
    if n.valid_to:
        s += f" $t < {n.valid_to.isoformat()};"
    return s


def _fun(name: str, body: list[str], comment: str) -> str:
    lines = "\n    ".join(x for x in body if x)
    return f"  # {comment}\n  fun {name}($c: claim) -> {{ claim }}:\n  match\n    {lines}\n  return {{ $c }};\n"


def _call(norm_id: str, var: str) -> str:
    return f"let {var} in h_{_ident(norm_id)}($c);"


def compile_norms(norms: dict[str, Norm]) -> tuple[str, list[str]]:
    """define クエリと、定義する関数名の一覧。"""
    funs: list[str] = []
    names: list[str] = []
    for n in norms.values():
        fn = function_names(n)
        head = f"$c has claim-type {q(n.claim_type)};" if n.claim_type else "$c isa claim;"
        funs.append(_fun(fn["conds"], [head, _time_pattern(n), _cond_pattern(n.when, [0])],
                         f"{n.id} {n.label}（要件）"))
        # 否定ごとに別の変数名にする（同じ名前を複数の not で使うと REP44 になる）
        negs = [f"not {{ {_call(e.id, f'$z{i}')} }};"
                for i, e in enumerate(e for e in exceptions_of(norms, n.id) if e.category != "blocking")]
        funs.append(_fun(fn["holds"], [f"let $y in {fn['conds']}($c);", *negs],
                         f"{n.id} {n.label}（成立）層{n.layer}"))
        names += [fn["conds"], fn["holds"]]

    grounds = [n for n in norms.values() if n.category == "arising"]
    blocking = [n for n in norms.values() if n.category == "blocking"]

    def union(ns: list[Norm]) -> str:
        if len(ns) == 1:
            return _call(ns[0].id, "$y")
        return " or ".join("{ " + _call(n.id, "$y") + " }" for n in ns) + ";"

    funs.append(_fun("ground_holds", [union(grounds)], "請求原因が成立し、消滅・障害の抗弁が成立しない"))
    if blocking:
        funs.append(_fun("blocked", [union(blocking)], "阻止の抗弁が成立する"))
        funs.append(_fun("claim_granted", ["let $y in ground_holds($c);", "not { let $z in blocked($c); };"],
                         "請求を認める"))
        funs.append(_fun("claim_granted_in_exchange", ["let $y in ground_holds($c);", "let $x in blocked($c);"],
                         "引換給付で認める"))
        names += OUTCOME_FUNCTIONS
    else:
        funs.append(_fun("claim_granted", ["let $y in ground_holds($c);"], "請求を認める"))
        names += ["ground_holds", "claim_granted"]
    header = f"# legal-onto compiler: {len(norms)} norms, generated {date.today().isoformat()}\n"
    return header + "define\n" + "\n".join(funs), names


def installed_functions(driver: Driver, database: str = DATABASE) -> list[str]:
    with driver.transaction(database, TransactionType.READ) as tx:
        rows = tx.query("match $f isa compiled-function, has function-name $n; select $n;").resolve()
        return [r.get("n").get_value() for r in rows.as_concept_rows()]


def install(driver: Driver, norms: dict[str, Norm], database: str = DATABASE) -> str:
    """生成した関数で、前回コンパイルした関数を置き換える。生成した define クエリを返す。"""
    query, names = compile_norms(norms)
    old = installed_functions(driver, database)
    with driver.transaction(database, TransactionType.SCHEMA) as tx:
        if old:
            tx.query("undefine " + " ".join(f"fun {n};" for n in old)).resolve()
        tx.query(query).resolve()
        tx.commit()
    with driver.transaction(database, TransactionType.WRITE) as tx:
        tx.query("match $f isa compiled-function; delete $f;").resolve()
        tx.query("insert " + " ".join(f"$f{i} isa compiled-function, has function-name {q(n)};"
                                      for i, n in enumerate(names))).resolve()
        tx.commit()
    return query
