# 第12章 プロパティグラフ（Neo4j と Cypher）

プロパティグラフは、「点（ノード）」と「線（エッジ、リレーションシップ）」に属性（プロパティ）を付けてデータを表す方式です。Neo4j が代表的な製品で、問い合わせ言語 Cypher は、2024 年に国際標準になった GQL（ISO/IEC 39075）のもとになりました。

## 12.1 点と線に属性を付ける

| 要素 | 持てるもの | RDB でいうと |
|------|----------|------------|
| ノード | ラベル（複数可）、属性 | 行（ラベルはテーブル名に近い） |
| リレーションシップ | 型（1 つ）、向き、属性 | 外部キー、または中間テーブルの行 |

RDF との一番の違いは、**線に属性を付けられる**ことです。「山田は第一営業部に所属している（2024 年から、本務）」の「2024 年から、本務」を、所属の線そのものに持たせられます。

## 12.2 例題を Cypher で書く

```cypher
// ノード（ラベルは複数付けられる）
CREATE (yamada:Employee:RegularEmployee  {name: '山田'}),
       (sato:Employee:ContractEmployee   {name: '佐藤'}),
       (suzuki:Employee:RegularEmployee  {name: '鈴木'}),
       (tanaka:Employee:RegularEmployee  {name: '田中'}),
       (hq:Department     {name: '営業本部'}),
       (sales1:Department {name: '第一営業部'}),
       (sales2:Department {name: '第二営業部'}),
       (dev:Department    {name: '開発部'}),
       (x:Project {name: 'X'}),
       (y:Project {name: 'Y'}),

// 関係（向きと属性を持つ）
       (sales1)-[:SUB_OF]->(hq),
       (sales2)-[:SUB_OF]->(hq),
       (yamada)-[:MEMBER_OF]->(sales1),
       (sato)-[:MEMBER_OF]->(sales1),
       (suzuki)-[:MEMBER_OF]->(sales2),
       (tanaka)-[:MEMBER_OF]->(dev),
       (yamada)-[:ASSIGNED {role: 'leader', since: date('2026-04-01')}]->(x),
       (sato)-[:ASSIGNED   {role: 'member', since: date('2026-04-15')}]->(x),
       (suzuki)-[:ASSIGNED {role: 'leader', since: date('2026-05-01')}]->(y);
```

### 継承はラベルを重ねて表す

プロパティグラフには、クラスの継承の仕組みがありません。正社員のノードに `:Employee` と `:RegularEmployee` の 2 つのラベルを付けて、「社員でもあり正社員でもある」ことを表します。**「正社員は必ず社員でもある」という規則は、データを作る側が守る必要があります。**

### 3 者以上の関係

割り当ての役割は、ここでは線の属性 `role` にしました。役割が単なる文字列で済むならこれで十分です。役割そのものに情報（権限、単価など）を持たせたいときは、RDF と同じように割り当てをノードにします。

```cypher
CREATE (a:Assignment {since: date('2026-04-01')}),
       (a)-[:ASSIGNEE]->(yamada), (a)-[:PROJECT]->(x), (a)-[:ROLE]->(:Role {name: 'leader'})
```

## 12.3 Cypher で問い合わせる

Cypher は、ノードを `()`、線を `-[]->` で絵のように書くのが特徴です。

### Q1: 営業本部（配下を含む）に所属する社員

```cypher
MATCH (e:Employee)-[:MEMBER_OF]->(:Department)-[:SUB_OF*0..]->(:Department {name: '営業本部'})
RETURN e.name
```

`*0..` は「0 段以上たどる」という意味です。部署の階層が何段あっても、1 行で書けます。プロパティグラフは、このような**経路の探索**を高速に行うように作られています（ノードから隣のノードへ、索引を引かずに直接たどれる作りになっている製品が多い）。

### Q2: リーダーが承認できる社員

```cypher
MATCH (l:Employee)-[:ASSIGNED {role: 'leader'}]->(p:Project)<-[:ASSIGNED]-(m:Employee)
WHERE l <> m
RETURN l.name, m.name
```

この結果を「ルール」として残したいときは、アプリケーションがこのクエリを実行して `(l)-[:CAN_APPROVE]->(m)` という線を作るか、ビューのように毎回このクエリを使います。Cypher には、ルールを登録して自動で推論させる仕組みは標準ではありません。

### Q3: どのプロジェクトにも割り当てられていない社員

```cypher
MATCH (e:Employee)
WHERE NOT EXISTS { (e)-[:ASSIGNED]->(:Project) }
RETURN e.name
```

### 動かしてみる

この節のデータと問い合わせは [examples/neo4j/company.cypher](examples/neo4j/company.cypher) にあり、[examples/docker-compose.yml](examples/docker-compose.yml) で Neo4j 5（Community 版）を起動して実行できます（[examples/README.md](examples/README.md)）。

```bash
cd docs/userguide/examples
docker compose up -d neo4j
docker compose exec neo4j cypher-shell -f /examples/company.cypher
```

```
"Q1", "佐藤" / "Q1", "山田" / "Q1", "鈴木"
"Q2", "山田", "佐藤"
"Q3", "田中"
```

ブラウザで http://localhost:7474 を開くと、Neo4j Browser でグラフを図として見られます（`MATCH (n) RETURN n`）。

## 12.4 スキーマと推論の弱さを補う

プロパティグラフは「スキーマがなくても始められる」手軽さが魅力ですが、オントロジーとして使うには、意味と制約をどこかで補う必要があります。

| 補いたいもの | 方法 |
|------------|------|
| 必須の属性・一意性 | 製品の制約機能（Neo4j の一意性制約、存在制約など） |
| 継承 | ラベルを重ねる規約と、それを検査する仕組み |
| ルール・推論 | アプリケーションで実行して結果の線を作る。製品のプラグインを使う |
| 意味の定義 | 別途 RDF/OWL で定義し、対応づける（Neo4j には RDF を取り込むプラグインもある） |

## 12.5 得意なことと苦手なこと

| 得意 | 苦手 |
|------|------|
| 経路の探索（何段先までつながっているか、最短経路） | 継承・型の階層を表す仕組みがない |
| 線に属性を付けられ、モデルが直感的 | ルールによる推論は標準では持たない |
| スキーマなしで素早く始められる | 3 者以上の関係は、結局ノードにする必要がある |
| グラフアルゴリズム（中心性、コミュニティ検出）のライブラリが充実 | 標準（GQL）は新しく、製品ごとの差がまだ大きい |

**向いている用途**: 不正検知（取引のつながり）、推薦、ネットワーク・IT 資産の依存関係、ソーシャルグラフ。意味の厳密さより、つながりの探索が主役の用途です。

## まとめ

- プロパティグラフは、ラベルと属性を持つノードと、型・向き・属性を持つ線でデータを表す
- Cypher（と標準の GQL）は、経路を絵のように書け、階層や経路の探索に強い
- 継承・ルール・意味の定義は弱いので、規約や別の仕組みで補う

| 観点 | プロパティグラフ |
|------|----------------|
| スキーマ | なくても動く。制約は製品の機能で一部書ける |
| 継承 | ない。ラベルを重ねて表す |
| n 項関係 | 線の属性で済まなければノードにする |
| 推移的な関係 | 可変長パス `*0..` |
| ルール | 標準ではない。アプリケーションで実行して結果を保存 |
| 否定 | 閉世界（`NOT EXISTS`） |
| 標準化 | ISO GQL（2024）。openCypher |
