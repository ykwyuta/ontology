"""コマンドライン。

  legal-onto init-db [--recreate]                 データベースを作り、schema/*.tql を適用する
  legal-onto import-law LAW_ID [--since DATE] [--include-scheduled] [--replace]
                                                  e-Gov 法令API v2 から法令を版つきで取り込む
  legal-onto text PATH --at DATE                  ある時点の条文
  legal-onto refs PATH [--at DATE] [--reverse] [--transitive] [--with-containers]
                                                  PATH とその項・号からの参照（--reverse で被参照）
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from . import db, egov, lawxml, loader, versions


def cmd_init_db(a) -> None:
    with db.connect() as driver:
        db.init_database(driver, a.database, recreate=a.recreate)
    print(f"initialized database {a.database!r}")


def cmd_import_law(a) -> None:
    t0 = time.time()
    info, revs = egov.law_revisions(a.law_id)
    snaps = egov.snapshots(revs, include_scheduled=a.include_scheduled)
    if a.since:
        since = date.fromisoformat(a.since)
        # since 時点で有効な版から取り込む
        earlier = [s for s in snaps if s.enforcement_date <= since]
        snaps = ([earlier[-1]] if earlier else []) + [s for s in snaps if s.enforcement_date > since]
    print(f"{info['law_id']} {revs[0].law_title}: {len(snaps)} snapshots "
          f"({snaps[0].enforcement_date} .. {snaps[-1].enforcement_date})")
    parsed = []
    for r in snaps:
        parsed.append((r, lawxml.parse(egov.law_xml(r.law_revision_id), a.law_id)))
        print(f"  parsed {r.law_revision_id}", flush=True)
    law = versions.merge(parsed)
    with db.connect() as driver:
        if a.replace:
            loader.delete_law(driver, a.law_id, a.database)
        stats = loader.load(driver, law, info.get("law_type", "Act"), a.database)
    print(f"loaded {stats} in {time.time() - t0:.0f}s")


def _fmt_rows(rows) -> None:
    for r in rows:
        print(r)


def cmd_text(a) -> None:
    query = f"""
        match $p isa provision, has provision-path $root; $root == {loader.q(a.path)};
              {{ $x is $p; }} or {{ let $x in parts_transitively($p); }};
              $x has provision-path $path;
              let $v in text_at($x, {a.at});
              $v has body-text $t, has sentence-num $n;
        fetch {{ "path": $path, "n": $n, "text": $t }};"""
    with db.connect() as driver:
        res = db.rows(driver, query, a.database)
    for r in sorted(res, key=lambda r: (r["path"], r["n"])):
        print(f"{r['path']}  {r['text']}")


def cmd_refs(a) -> None:
    """PATH とその下位の規定（項・号）からの参照、または --reverse でそれらへの参照。"""
    role_self, role_other = ("cited", "citing") if a.reverse else ("citing", "cited")
    up = " or { let $p in containers_transitively($root); }" if a.with_containers else ""
    scope = f"""$root isa provision, has provision-path {loader.q(a.path)};
                  {{ $p is $root; }} or {{ let $p in parts_transitively($root); }}{up};"""
    if a.transitive:
        fn = ("citing" if a.reverse else "referenced") + ("_at" if a.at else "_transitively")
        args = f"$p, {a.at}" if a.at else "$p"
        query = f"""
            match {scope}
                  let $q in {fn}({args});
                  $q has provision-path $path;
            fetch {{ "path": $path }};"""
    else:
        active = f"let $y in reference_active($r, {a.at});" if a.at else ""
        query = f"""
            match {scope}
                  $r isa cross-reference, links ({role_self}: $p, {role_other}: $q), has reference-kind $k;
                  {active}
                  $p has provision-path $from; $q has provision-path $path;
            fetch {{ "path": $path, "kind": $k, "via": $from }};"""
    with db.connect() as driver:
        res = db.rows(driver, query, a.database)
    if a.transitive:
        for path in sorted({r["path"] for r in res}):
            print(path)
        return
    lines = {(r["path"], r["via"], r["kind"]) if a.reverse else (r["via"], r["path"], r["kind"]) for r in res}
    for citing, cited, kind in sorted(lines):
        print(f"{citing} -> {cited}  ({kind})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legal-onto")
    ap.add_argument("--database", default=db.DATABASE)
    sub = ap.add_subparsers(required=True)

    p = sub.add_parser("init-db")
    p.add_argument("--recreate", action="store_true")
    p.set_defaults(fn=cmd_init_db)

    p = sub.add_parser("import-law")
    p.add_argument("law_id")
    p.add_argument("--since", help="この日に有効な版以降を取り込む（YYYY-MM-DD）")
    p.add_argument("--include-scheduled", action="store_true", help="未施行の改正も取り込む")
    p.add_argument("--replace", action="store_true", help="取り込み済みの同じ法令を削除してから取り込む")
    p.set_defaults(fn=cmd_import_law)

    p = sub.add_parser("text")
    p.add_argument("path")
    p.add_argument("--at", default=date.today().isoformat())
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("refs")
    p.add_argument("path")
    p.add_argument("--at")
    p.add_argument("--reverse", action="store_true")
    p.add_argument("--transitive", action="store_true")
    p.add_argument("--with-containers", action="store_true",
                   help="PATH を含む条・編章節への参照も含める（「この節の規定は…準用する」など）")
    p.set_defaults(fn=cmd_refs)

    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
