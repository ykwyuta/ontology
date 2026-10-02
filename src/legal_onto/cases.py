"""事案（cases/*.yaml）の取り込みと評価、評価結果の報告。

事案の書式:
  case-id: demo-001
  description: 説明
  claims:
    - id: demo-001-price          # 訴訟物ID
      type: sale-price            # 規範の claim-type
      claimant: X
      respondent: Y
      time-points:                # 規範の time-anchor ごとの日付
        declaration: 2024-05-10
      facts:                      # fact-code: admitted / proven / unclear / disproven
        N555.contract-concluded: admitted
      expect: granted             # テスト用（granted / granted-in-exchange / denied）

結論は TypeDB の生成関数（compiler.py）で求める。報告の組み立て（どの規範が成立したか、不足事実、警告）は、
規範ごとの関数の結果と norms/*.yaml の構造から Python で行う。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from typedb.driver import Driver, TransactionType

from .compiler import function_names, installed_functions
from .db import DATABASE
from .loader import q
from .norms import Cond, Norm, exceptions_of

PROOF_STATUSES = {"admitted", "proven", "unclear", "disproven"}
STATUS_JA = {"admitted": "自白", "proven": "証明済", "unclear": "真偽不明", "disproven": "否定", None: "主張なし"}
BURDEN_JA = {"claimant": "請求する側", "respondent": "請求される側"}
LAYER_JA = ["請求原因", "抗弁", "再抗弁", "再々抗弁"]
OUTCOME_JA = {"granted": "請求を認める", "granted-in-exchange": "引換給付で請求を認める", "denied": "請求を認めない"}
DISCLAIMER = ("この結果は、登録した規範と入力した事実の証明状態から機械的に導いたもので、論点の整理と立証計画の補助を目的とする。"
              "法的判断は利用者が行うこと。規範は法律の専門家による確認を経ていない（review-status を参照）。")


class CaseError(ValueError):
    pass


@dataclass
class Claim:
    id: str
    type: str
    claimant: str
    respondent: str
    time_points: dict[str, date] = field(default_factory=dict)
    facts: dict[str, str] = field(default_factory=dict)
    expect: str | None = None


@dataclass
class Case:
    id: str
    description: str
    claims: list[Claim]


def parse_case(path: Path) -> Case:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    claims = []
    for c in d.get("claims", []):
        facts = {str(k): str(v) for k, v in (c.get("facts") or {}).items()}
        for k, v in facts.items():
            if v not in PROOF_STATUSES:
                raise CaseError(f"{path.name}: {c['id']} の事実 {k} の証明状態 {v!r} は {sorted(PROOF_STATUSES)} のどれか")
        claims.append(Claim(
            id=str(c["id"]), type=str(c["type"]), claimant=str(c["claimant"]), respondent=str(c["respondent"]),
            time_points={str(k): v if isinstance(v, date) else date.fromisoformat(str(v))
                         for k, v in (c.get("time-points") or {}).items()},
            facts=facts, expect=c.get("expect")))
    return Case(str(d["case-id"]), str(d.get("description", "")), claims)


def store_case(driver: Driver, case: Case, database: str = DATABASE) -> None:
    """同じ case-id の事案があれば置き換える。"""
    with driver.transaction(database, TransactionType.WRITE) as tx:
        cid = q(case.id)
        for t in ("fact-finding", "time-point"):
            tx.query(f"""match $k isa case-file, has case-id {cid}; case-membership (case: $k, member: $c);
                         $c isa claim; $x isa {t}, links (subject: $c); delete $x;""").resolve()
        tx.query(f"""match $k isa case-file, has case-id {cid}; case-membership (case: $k, member: $x);
                     delete $x;""").resolve()
        tx.query(f"match $k isa case-file, has case-id {cid}; delete $k;").resolve()

        out = [f"$k isa case-file, has case-id {cid}, has procedure-type \"civil\";"]
        parties: dict[str, str] = {}
        for c in case.claims:
            for name in (c.claimant, c.respondent):
                if name not in parties:
                    parties[name] = f"$p{len(parties)}"
                    out.append(f"{parties[name]} isa party, has party-name {q(name)}; "
                               f"case-membership (case: $k, member: {parties[name]});")
        for i, c in enumerate(case.claims):
            v = f"$c{i}"
            out.append(f"{v} isa claim, has claim-id {q(c.id)}, has claim-type {q(c.type)}; "
                       f"case-membership (case: $k, member: {v}); "
                       f"claim-party (claim: {v}, claimant: {parties[c.claimant]}, respondent: {parties[c.respondent]});")
            for j, (anchor, at) in enumerate(c.time_points.items()):
                out.append(f"time-point (subject: {v}), has anchor-code {q(anchor)}, has at {at.isoformat()};")
            for code, status in c.facts.items():
                out.append(f"fact-finding (subject: {v}), has fact-code {q(code)}, has proof-status {q(status)};")
        tx.query("insert " + "\n".join(out)).resolve()
        tx.commit()


def _members(driver: Driver, function: str, claim_ids: list[str], database: str) -> set[str]:
    with driver.transaction(database, TransactionType.READ) as tx:
        rows = tx.query(f"match $c isa claim, has claim-id $id; let $y in {function}($c); select $id;").resolve()
        return {r.get("id").get_value() for r in rows.as_concept_rows()} & set(claim_ids)


def check_installed(driver: Driver, norms: dict[str, Norm], database: str = DATABASE) -> None:
    """DB にコンパイル済みの関数が、norms/*.yaml と対応しているか。"""
    have = set(installed_functions(driver, database))
    want = {f for n in norms.values() for f in function_names(n).values()}
    if not want <= have:
        raise CaseError("norms/*.yaml がコンパイルされていない。legal-onto load-norms を実行すること: "
                        + ", ".join(sorted(want - have)[:5]))


@dataclass
class ClaimResult:
    claim: Claim
    outcome: str
    conds: set[str]          # 要件を満たす規範
    holds: set[str]          # 成立する規範


def evaluate(driver: Driver, case: Case, norms: dict[str, Norm], database: str = DATABASE) -> list[ClaimResult]:
    check_installed(driver, norms, database)
    ids = [c.id for c in case.claims]
    have = set(installed_functions(driver, database))
    granted = _members(driver, "claim_granted", ids, database)
    exchange = _members(driver, "claim_granted_in_exchange", ids, database) if "claim_granted_in_exchange" in have else set()
    conds: dict[str, set[str]] = {i: set() for i in ids}
    holds: dict[str, set[str]] = {i: set() for i in ids}
    for n in norms.values():
        fn = function_names(n)
        for i in _members(driver, fn["conds"], ids, database):
            conds[i].add(n.id)
        for i in _members(driver, fn["holds"], ids, database):
            holds[i].add(n.id)
    results = []
    for c in case.claims:
        outcome = "granted" if c.id in granted else "granted-in-exchange" if c.id in exchange else "denied"
        results.append(ClaimResult(c, outcome, conds[c.id], holds[c.id]))
    return results


# --- 報告 ---

def _established(status: str | None) -> bool:
    return status in ("admitted", "proven")


def _all_facts(n: Norm, norms: dict[str, Norm]) -> list[Cond]:
    """要件として使う規範の要件事実を含む。"""
    return n.when.facts() + [f for r in n.when.norm_refs() for f in _all_facts(norms[r], norms)]


def _in_play(n: Norm, claim: Claim, norms: dict[str, Norm]) -> bool:
    """争点になっているか: この規範に固有の要件事実（他の規範と共有しないもの）が 1 つでも入力されている。

    「取消しの意思表示」のように複数の抗弁に共通する事実だけでは、詐欺・強迫などを争点として扱わない。
    """
    shared: dict[str, int] = {}
    for m in norms.values():
        if m.category != "auxiliary":
            for code in {f.code for f in _all_facts(m, norms)}:
                shared[code] = shared.get(code, 0) + 1
    own = [f for f in _all_facts(n, norms) if shared.get(f.code, 0) <= 1]
    if not own:   # 固有の事実がない規範は、事実が 1 つでも入力されていれば争点とする
        own = _all_facts(n, norms)
    return any(f.code in claim.facts for f in own)


def _render_cond(c: Cond, claim: Claim, r: ClaimResult, norms: dict[str, Norm], indent: str, lines: list[str]) -> None:
    if c.kind == "fact":
        st = claim.facts.get(c.code)
        mark = "✓" if _established(st) else "?" if st == "unclear" else "✗" if st == "disproven" else "-"
        ev = "、規範的要件: 評価は利用者の入力" if c.evaluative else ""
        lines.append(f"{indent}{mark} {c.label}［{STATUS_JA[st]}{ev}］ ({c.code})")
    elif c.kind == "norm":
        m = norms[c.code]
        mark = "✓" if m.id in r.holds else "✗"
        lines.append(f"{indent}{mark} 〔{m.id} {m.label}〕が成立すること")
        _render_cond(m.when, claim, r, norms, indent + "    ", lines)
        for e in exceptions_of(norms, m.id):
            _render_norm(e, claim, r, norms, indent + "    ", lines)
    else:
        lines.append(f"{indent}{'次のすべて' if c.kind == 'all' else '次のいずれか'}:")
        for x in c.children:
            _render_cond(x, claim, r, norms, indent + "  ", lines)


def _render_norm(n: Norm, claim: Claim, r: ClaimResult, norms: dict[str, Norm], indent: str,
                 lines: list[str]) -> None:
    if n.category != "arising" and not _in_play(n, claim, norms):
        return
    state = "成立" if n.id in r.holds else "要件充足・例外により不成立" if n.id in r.conds else "不成立"
    layer = LAYER_JA[n.layer] if n.layer < len(LAYER_JA) else f"層{n.layer}"
    lines.append(f"{indent}[{state}] {n.id} {n.label}（{layer}・立証責任: {BURDEN_JA[n.burden]}）")
    _render_cond(n.when, claim, r, norms, indent + "    ", lines)
    for e in exceptions_of(norms, n.id):
        _render_norm(e, claim, r, norms, indent + "  ", lines)


def _reachable(claim: Claim, norms: dict[str, Norm]) -> list[Norm]:
    out: dict[str, Norm] = {}

    def walk(n: Norm) -> None:
        if n.id in out:
            return
        out[n.id] = n
        for ref in n.when.norm_refs():
            walk(norms[ref])
        for e in exceptions_of(norms, n.id):
            walk(e)

    for n in norms.values():
        if n.category == "arising" and n.claim_type == claim.type:
            walk(n)
    return list(out.values())


def report(r: ClaimResult, norms: dict[str, Norm]) -> str:
    c = r.claim
    lines = [f"■ 訴訟物 {c.id}（{c.type}）: {c.claimant} → {c.respondent}",
             f"  結論: {OUTCOME_JA[r.outcome]}"]
    reachable = _reachable(c, norms)
    reasons = [n for n in reachable if n.layer == 1 and n.id in r.holds]
    grounds = [n for n in reachable if n.category == "arising"]
    if r.outcome == "denied":
        if not any(g.id in r.conds for g in grounds):
            lines.append("  理由: 請求原因の要件事実が証明されていない")
        elif reasons:
            lines.append("  理由: 抗弁が成立する — " + "、".join(f"{n.id} {n.label}" for n in reasons))
    elif r.outcome == "granted-in-exchange":
        lines.append("  理由: 阻止の抗弁が成立する — " + "、".join(f"{n.id} {n.label}" for n in reasons))

    lines.append("")
    lines.append("  論証（事実が入力された規範のみ表示）:")
    for g in grounds:
        _render_norm(g, c, r, norms, "    ", lines)

    # 不足事実: 争点になっている規範で、証明されていない要件事実
    # 例外として働く規範は、その対象の規範の要件が満たされているときだけ結論に影響する
    missing = []
    for n in reachable:
        if n.category == "auxiliary" or not _in_play(n, c, norms) or n.id in r.conds:
            continue
        if n.exception_of and not any(b in r.conds for b in n.exception_of):
            continue
        for f in _all_facts(n, norms):
            if not _established(c.facts.get(f.code)):
                missing.append((n, f))
    if missing:
        lines.append("")
        lines.append("  結論を変えうる立証（要件を満たしていない規範の、証明されていない要件事実）:")
        for n, f in missing:
            lines.append(f"    - {BURDEN_JA[n.burden]}: {f.label}［{STATUS_JA[c.facts.get(f.code)]}］"
                         f"（{n.id} {n.label}）")

    warnings = []
    known = {f.code for n in norms.values() for f in n.when.facts()}
    for code in c.facts:
        if code not in known:
            warnings.append(f"規範にない要件事実が入力されている: {code}")
    for n in reachable:
        if not (n.valid_from or n.valid_to) or not _in_play(n, c, norms):
            continue
        at = c.time_points.get(n.time_anchor)
        if at is None:
            warnings.append(f"{n.id} {n.label}: 時点 {n.time_anchor} が未入力のため適用していない")
        elif (n.valid_from and at < n.valid_from) or (n.valid_to and at >= n.valid_to):
            warnings.append(f"{n.id} {n.label}: 時点 {n.time_anchor}={at} は適用期間外"
                            f"（{n.valid_from or ''}〜{n.valid_to or ''}）。この時点に適用される規範（旧法など）は未登録")
    used = [n for n in reachable if n.id in r.holds or n.id in r.conds]
    unreviewed = [n for n in used if n.review_status in ("unreviewed", "disputed")]
    if unreviewed:
        warnings.append("専門家の確認を経ていない規範を使っている: "
                        + "、".join(f"{n.id}（{n.review_status}）" for n in unreviewed))
    evaluative = [f for n in used for f in n.when.facts() if f.evaluative and _established(c.facts.get(f.code))]
    if evaluative:
        warnings.append("利用者の評価に依存する規範的要件: " + "、".join(f.label for f in evaluative))
    if warnings:
        lines.append("")
        lines.append("  注意:")
        lines += [f"    ! {w}" for w in warnings]
    return "\n".join(lines)


def report_case(case: Case, results: list[ClaimResult], norms: dict[str, Norm]) -> str:
    out = [f"事案 {case.id}" + (f": {case.description}" if case.description else ""), ""]
    for r in results:
        out.append(report(r, norms))
        out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)
