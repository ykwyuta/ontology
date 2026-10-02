"""提案書 04-schema-design.md の TypeQL を実機の TypeDB で検証する。

文書中の define ブロックは節をまたいで相互に参照するため、1 つのスキーマトランザクションにまとめて定義する。
その後、insert ブロックと読み取りクエリを順に実行する（クエリは構文・型検査の確認が目的で、結果の行数は問わない）。

使い方: python scripts/verify_proposal_typeql.py [--keep]
"""

# 4.5 の例題事案。{rebuttal_exc} に 95条3項1号の事実の証明状態を入れる
DEMO_CASE = """
insert
  $case isa case-file, has case-id "2026-demo-001", has procedure-type "civil";
  $x isa party, has party-name "X";
  $y isa party, has party-name "Y";
  $c isa sales-contract, links (seller: $x, buyer: $y), has price 3000000, has concluded-on 2024-05-10;
  $d isa declaration-of-intent, has declared-on 2024-05-10;
  contract-declaration (contract: $c, declaration: $d, declarant: $y);
  $f0 isa fact-finding, links (subject: $c), has fact-code "N555.contract-concluded", has proof-status "admitted";
  $f1 isa fact-finding, links (subject: $d), has fact-code "N95-1.material", has proof-status "proven";
  $f2 isa fact-finding, links (subject: $d), has fact-code "N95-1-2.mistake-in-motive", has proof-status "proven";
  $f3 isa fact-finding, links (subject: $d), has fact-code "N95-2.motive-indicated", has proof-status "proven";
  $f4 isa fact-finding, links (subject: $d), has fact-code "N123.cancellation-declared", has proof-status "admitted";
  $f5 isa fact-finding, links (subject: $d), has fact-code "N95-3.gross-negligence", has proof-status "proven";
  $f6 isa fact-finding, links (subject: $d), has fact-code "N95-3-1.counterparty-knew-or-gross-negligence",
      has proof-status "{rebuttal_exc}";
  case-membership (case: $case, member: $c);
  case-membership (case: $case, member: $d);
  case-membership (case: $case, member: $f0); case-membership (case: $case, member: $f1);
  case-membership (case: $case, member: $f2); case-membership (case: $case, member: $f3);
  case-membership (case: $case, member: $f4); case-membership (case: $case, member: $f5);
  case-membership (case: $case, member: $f6);
"""
import re
import sys
from pathlib import Path

from typedb.driver import Credentials, DriverOptions, DriverTlsConfig, TransactionType, TypeDB

DOC = Path(__file__).resolve().parents[1] / "docs/proposal/04-schema-design.md"
DB = "proposal-verify"

# 文書では「同じパターンで生成する」として省略している関数のスタブ
STUBS = """
  fun defence_payment() -> { sales-contract }:
  match
    $c isa sales-contract;
    $f isa fact-finding, links (subject: $c), has fact-code "N473.paid";
    let $f in established();
  return { $c };

  fun defence_prescription() -> { sales-contract }:
  match
    $c isa sales-contract;
    $f isa fact-finding, links (subject: $c), has fact-code "N166.prescription-invoked";
    let $f in established();
  return { $c };
"""


def run(driver, tt, label, q, expect=None):
    try:
        with driver.transaction(DB, tt) as tx:
            ans = tx.query(q).resolve()
            if ans.is_concept_documents():
                out = f"{len(list(ans.as_concept_documents()))} docs"
            elif ans.is_concept_rows():
                out = f"{len(list(ans.as_concept_rows()))} rows"
            else:
                out = ""
            if tt != TransactionType.READ:
                tx.commit()
        if expect is not None and not out.startswith(f"{expect} "):
            print(f"FAIL {label}: expected {expect}, got {out}")
            return False
        print(f"OK   {label} {out}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"FAIL {label}: {str(e).strip()[:2000]}")
        return False


def main() -> int:
    blocks = re.findall(r"```typeql\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)
    defines = [b for b in blocks if b.lstrip().startswith("define")]
    others = [b for b in blocks if not b.lstrip().startswith("define")]
    schema = "define\n" + "\n".join(re.sub(r"^\s*define\s*\n", "", b) for b in defines) + STUBS

    driver = TypeDB.driver("127.0.0.1:1729", Credentials("admin", "password"),
                           DriverOptions(DriverTlsConfig.disabled()))
    if driver.databases.contains(DB):
        driver.databases.get(DB).delete()
    driver.databases.create(DB)

    ok = run(driver, TransactionType.SCHEMA, "schema (all define blocks)", schema)
    for q in others:
        head = q.strip().splitlines()[0:2]
        writes = re.search(r"^\s*(insert|delete|update|put)\b", q, re.M)
        tt = TransactionType.WRITE if writes else TransactionType.READ
        ok &= run(driver, tt, " | ".join(s.strip() for s in head), q)

    # 意味の検証: 4.5 の例題で Q1（結論）・Q2（不足事実）が文書どおりになるか
    q1, q2 = others[1], others[2]
    for status, granted, missing in (("unclear", 1, 1), ("proven", 0, 0)):
        with driver.transaction(DB, TransactionType.WRITE) as tx:
            tx.query("match $x isa case-file; delete $x;").resolve()
            for t in ("fact-finding", "sales-contract", "declaration-of-intent", "party"):
                tx.query(f"match $x isa {t}; delete $x;").resolve()
            tx.query(DEMO_CASE.replace("{rebuttal_exc}", status)).resolve()
            tx.commit()
        ok &= run(driver, TransactionType.READ, f"Q1 (95-3-1 {status}) granted", q1, granted)
        ok &= run(driver, TransactionType.READ, f"Q2 (95-3-1 {status}) missing facts", q2, missing)

    if "--keep" not in sys.argv:
        driver.databases.get(DB).delete()
    driver.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
