# 第3部の例題を動かす

第10章の例題（社員・部署・プロジェクト）と 3 つの問いを、各方式で実際に動かすための環境です。

| 方式 | 章 | ファイル | 動かし方 |
|------|----|---------|---------|
| プロパティグラフ（Neo4j 5 / Cypher） | 12 | [neo4j/company.cypher](neo4j/company.cypher) | この docker compose |
| Datalog（Soufflé 2.5） | 14 | [souffle/company.dl](souffle/company.dl) | この docker compose |
| TypeDB（TypeQL） | 13 | 第13章のコード | リポジトリ直下の docker compose（TypeDB 3.13） |
| RDF（SPARQL） | 11 | 第11章のコード | 任意のトリプルストア、または Python の rdflib |
| RDB（SQL） | 15 | 第15章のコード | PostgreSQL・SQLite など（`WITH RECURSIVE` に対応したもの） |

## 前提

- Docker（compose v2）
- Soufflé のイメージは、公式リリースの Ubuntu 24.04 向けパッケージ（x86_64）から作ります。初回だけビルドに数分かかります

## Neo4j（Cypher）

```bash
cd docs/userguide/examples
docker compose up -d neo4j
docker compose exec neo4j cypher-shell -f /examples/company.cypher
```

期待する結果:

```
q, name
"Q1", "佐藤"
"Q1", "山田"
"Q1", "鈴木"
q, leader, member
"Q2", "山田", "佐藤"
q, name
"Q3", "田中"
```

- 起動直後は接続できないことがあります。`docker compose ps` で `healthy` になってから実行してください
- Windows の Git Bash では、パスが書き換えられて `/examples/company.cypher` が見つからないことがあります。その場合は先頭に `MSYS_NO_PATHCONV=1` を付けて実行してください
- http://localhost:7474 で Neo4j Browser が開きます（認証なし）。`MATCH (n) RETURN n` でグラフを図として見られます

## Soufflé（Datalog）

```bash
cd docs/userguide/examples
docker compose run --rm souffle
```

期待する結果:

```
---------------
can_approve
leader	member
===============
山田	佐藤
===============
---------------
in_sales_hq
e
===============
山田
佐藤
鈴木
===============
---------------
unassigned
e
===============
田中
===============
```

プログラムを書き換えたら、もう一度 `docker compose run --rm souffle` を実行するだけで結果が出ます（ファイルはコンテナに読み取り専用でマウントしています）。

## 片づけ

```bash
docker compose down
```

## 確認済みの環境

2026-10-03 に、Windows 11 + Docker Desktop で、上の期待どおりの結果が出ることを確認しました（Neo4j 5.26.31 Community、Soufflé 2.5）。
