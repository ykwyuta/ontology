# 第11章 RDF と OWL・SPARQL

RDF は、オントロジーを表す方式としてもっとも歴史があり、標準化が進んでいる方式です。W3C（Web の標準化団体）が仕様を定めています。

## 11.1 すべてを三つ組で表す

RDF では、すべての情報を**主語・述語・目的語**の三つ組（トリプル）で表します。

| 主語 | 述語 | 目的語 |
|-----|------|-------|
| 山田 | 種類は | 正社員 |
| 山田 | 名前 | "山田" |
| 山田 | 所属 | 第一営業部 |
| 第一営業部 | 上位部署 | 営業本部 |

主語・述語・目的語には URI（第6章）を使います。目的語は、別のモノ（URI）か値（文字列・数値・日付）です。

RDB に置き換えると、**列が 3 つしかない巨大な 1 枚のテーブル**だと考えるとイメージしやすいでしょう。スキーマを先に決めなくても、どんな情報でも三つ組として追加できます。

## 11.2 例題を Turtle で書く

Turtle は、RDF を人が読み書きしやすくした記法です。

```turtle
@prefix ex:   <https://example.com/> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

# --- スキーマ（オントロジー） ---
ex:RegularEmployee  rdfs:subClassOf ex:Employee .
ex:ContractEmployee rdfs:subClassOf ex:Employee .
ex:memberOf         rdfs:domain ex:Employee ; rdfs:range ex:Department .
ex:subDepartmentOf  a owl:TransitiveProperty .      # 推移的な関係

# --- データ ---
ex:yamada a ex:RegularEmployee  ; ex:name "山田" ; ex:memberOf ex:sales1 .
ex:sato   a ex:ContractEmployee ; ex:name "佐藤" ; ex:memberOf ex:sales1 .
ex:suzuki a ex:RegularEmployee  ; ex:name "鈴木" ; ex:memberOf ex:sales2 .
ex:tanaka a ex:RegularEmployee  ; ex:name "田中" ; ex:memberOf ex:dev .

ex:sales1 a ex:Department ; ex:name "第一営業部" ; ex:subDepartmentOf ex:salesHQ .
ex:sales2 a ex:Department ; ex:name "第二営業部" ; ex:subDepartmentOf ex:salesHQ .
ex:salesHQ a ex:Department ; ex:name "営業本部" .
ex:dev    a ex:Department ; ex:name "開発部" .
```

`a` は「種類は」（`rdf:type`）の略です。`;` で同じ主語の三つ組を続けて書けます。

### 3 者以上の関係（割り当て）

三つ組は二者の関係しか表せないので、「割り当て」そのものをモノ（ノード）として作り、そこから各参加者へ線を引きます。第3章で見た「関係を独立したモノとして扱う」考え方です。

```turtle
ex:asg1 a ex:Assignment ;
    ex:assignee ex:yamada ; ex:project ex:projX ; ex:role ex:Leader ;
    ex:since "2026-04-01"^^xsd:date .
ex:asg2 a ex:Assignment ;
    ex:assignee ex:sato ; ex:project ex:projX ; ex:role ex:Member ;
    ex:since "2026-04-15"^^xsd:date .
ex:asg3 a ex:Assignment ;
    ex:assignee ex:suzuki ; ex:project ex:projY ; ex:role ex:Leader ;
    ex:since "2026-05-01"^^xsd:date .
```

> 二者の関係そのものに属性を付けたいとき（「所属」に開始日を付けるなど）は、この方法のほかに、三つ組を主語にして三つ組を作る RDF-star（RDF 1.2 で標準化が進められている「三つ組についての三つ組」）という方法もあります。

## 11.3 SPARQL で問い合わせる

SPARQL は RDF の問い合わせ言語です。三つ組のパターンを書き、変数（`?x`）に当てはまるものを探します。

### Q1: 営業本部（配下を含む）に所属する社員

```sparql
PREFIX ex:   <https://example.com/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?name WHERE {
  ?e a/rdfs:subClassOf* ex:Employee ;      # 社員の子クラスも含む
     ex:name ?name ;
     ex:memberOf ?d .
  ?d ex:subDepartmentOf* ex:salesHQ .      # 0 段以上たどる（営業本部そのものも含む）
}
```

`*` は**プロパティパス**で、「0 回以上たどる」という意味です。推移的な関係や継承を、クエリの中で簡単に書けます。推論機能を持つトリプルストアなら、`rdfs:subClassOf` や `owl:TransitiveProperty` をデータベースが解釈し、`?e a ex:Employee` と書くだけで子クラスも含めてくれます。

### Q2: リーダーが承認できる社員

```sparql
SELECT ?leaderName ?memberName WHERE {
  ?a1 ex:assignee ?l ; ex:project ?p ; ex:role ex:Leader .
  ?a2 ex:assignee ?m ; ex:project ?p .
  FILTER (?l != ?m)
  ?l ex:name ?leaderName . ?m ex:name ?memberName .
}
```

ルールとして保存したい場合は、`CONSTRUCT` で新しい三つ組（`?l ex:canApprove ?m`）を作って保存するか、SHACL のルール機能や製品独自のルール機能（SWRL など）を使います。標準の SPARQL 自体には、「ルールを登録しておいて自動で使う」仕組みはありません。

### Q3: どのプロジェクトにも割り当てられていない社員

```sparql
SELECT ?name WHERE {
  ?e a/rdfs:subClassOf* ex:Employee ; ex:name ?name .
  FILTER NOT EXISTS { ?a ex:assignee ?e }
}
```

## 11.4 OWL: 意味をもっと厳密に書く

OWL（Web Ontology Language）は、RDF の上でクラスや関係の意味を論理的に定義する言語です。記述論理という論理体系に基づいていて、推論エンジン（リーズナー）が、矛盾の検出や自動分類を行えます。

```turtle
# 「リーダーとは、役割がリーダーである割り当てを1つ以上持つ社員」
ex:ProjectLeader owl:equivalentClass [
    a owl:Class ;
    owl:intersectionOf ( ex:Employee
        [ a owl:Restriction ; owl:onProperty ex:hasAssignment ;
          owl:someValuesFrom [ a owl:Restriction ; owl:onProperty ex:role ; owl:hasValue ex:Leader ] ] )
] .
```

このように定義しておくと、リーズナーが条件を満たす社員を自動的に `ex:ProjectLeader` に分類します（第4章の「条件で定義されたクラス」）。

### OWL は開世界

OWL は開世界仮定（第5章）で動きます。たとえば「社員は所属を 1 つだけ持つ」と定義していて、ある社員に所属が書かれていなくても、OWL は「違反」とはみなしません（書いていないだけかもしれないので）。逆に所属が 2 つあれば、「2 つの部署は同じものだ」と推論することさえあります。

業務システムの感覚でいう「必須チェック」をしたいときは、**SHACL**（Shapes Constraint Language）を使います。SHACL は閉世界でデータを検証する W3C の標準です。

```turtle
ex:EmployeeShape a sh:NodeShape ;
    sh:targetClass ex:Employee ;
    sh:property [ sh:path ex:memberOf ; sh:minCount 1 ; sh:maxCount 1 ] .
```

**OWL で意味を定義し、SHACL でデータを検証する**、という使い分けが一般的です。

## 11.5 得意なことと苦手なこと

| 得意 | 苦手 |
|------|------|
| 標準化されている（RDF・OWL・SPARQL・SHACL）。製品を選べ、データを移しやすい | 3 者以上の関係や、関係の属性を書くと冗長になる |
| URI で世界中のデータとつながる（公開データ、Wikidata など） | 業務の否定（閉世界）や例外のルールは、OWL では書きにくい |
| スキーマなしでも始められ、あとから意味を足せる | 性能のチューニングに RDB とは違う知識が要る |
| 標準の語彙（schema.org、FIBO、SNOMED CT など）が豊富 | 学習する仕様が多い |

## まとめ

- RDF はすべてを主語・述語・目的語の三つ組で表す。URI で世界とつながる
- SPARQL のプロパティパスで、継承や推移的な関係を簡単にたどれる
- OWL で意味を厳密に定義し、リーズナーで自動分類・矛盾検出ができる。ただし開世界
- データの必須チェックなど閉世界の検証は SHACL で行う

| 観点 | RDF / OWL / SPARQL |
|------|-------------------|
| スキーマ | なくても動く。OWL・RDFS で意味を、SHACL で制約を書く |
| 継承 | `rdfs:subClassOf`。推論機能か `subClassOf*` で子クラスを含める |
| n 項関係 | 関係をノードにして表す（やや冗長） |
| 推移的な関係 | `owl:TransitiveProperty`、プロパティパス `*` |
| ルール | OWL の定義、SHACL ルール、製品独自のルール |
| 否定 | OWL は開世界。SPARQL の `FILTER NOT EXISTS` は閉世界 |
| 標準化 | W3C 標準。製品が多い |
