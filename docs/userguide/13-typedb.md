# 第13章 型付きハイパーグラフ（TypeDB と TypeQL）

TypeDB は、このリポジトリで使っているデータベースです。エンティティ・リレーション・属性という 3 種類の型でデータを表し、強い型システムと、関数による推論を持っています。本章のコードは TypeDB 3.x（このリポジトリでは 3.13）の構文です。

## 13.1 3 種類の型

| 型 | 意味 | RDB でいうと | 例 |
|----|------|------------|-----|
| エンティティ（entity） | 独立して存在するモノ | エンティティのテーブル | 社員、部署、プロジェクト |
| リレーション（relation） | ロールを通じて他のものを結ぶ関係 | 中間テーブル | 所属、割り当て |
| 属性（attribute） | 値 | 列 | 名前、開始日 |

TypeDB の特徴は次の 3 点です。

1. **関係が最初から n 項で、ロールを持つ**（第3章の考え方そのまま）。RDF やプロパティグラフのように、関係をノードに置き換える工夫が要りません
2. **継承がエンティティ・リレーション・属性のすべてにある**。親の型で問い合わせると、子の型も自動で含まれます
3. **スキーマが必須で、型の検査が厳しい**。存在しない型やロールを使ったクエリは、実行前にエラーになります（Java のコンパイルエラーに近い感覚です）

## 13.2 例題を TypeQL で書く

### スキーマ

```typeql
define
  attribute name, value string;
  attribute role-name, value string;
  attribute since, value date;

  entity employee @abstract,
    owns name,
    plays membership:member,
    plays assignment:assignee;
  entity regular-employee sub employee;      # 継承
  entity contract-employee sub employee;

  entity department,
    owns name,
    plays membership:unit,
    plays department-hierarchy:parent,
    plays department-hierarchy:child;

  entity project,
    owns name,
    plays assignment:project;

  relation membership, relates member, relates unit;
  relation department-hierarchy, relates parent, relates child;
  relation assignment,                       # 社員・プロジェクトを結び、属性を持つ関係
    relates assignee, relates project,
    owns role-name, owns since;
```

`plays membership:member` は「社員は、所属という関係の中で member というロールを担える」という宣言です。どの型がどのロールを担えるかをスキーマで決めるので、間違った組み合わせのデータは入りません。

> 役割（リーダー・メンバー）を文字列の属性 `role-name` にしましたが、役割を担う人ごとにロールを分けて `relates leader, relates member` と書く方法もあります。どちらにするかは、問い合わせ方で決めます。

### データ

```typeql
insert
  $yamada isa regular-employee, has name "山田";
  $sato   isa contract-employee, has name "佐藤";
  $suzuki isa regular-employee, has name "鈴木";
  $tanaka isa regular-employee, has name "田中";
  $hq     isa department, has name "営業本部";
  $sales1 isa department, has name "第一営業部";
  $sales2 isa department, has name "第二営業部";
  $dev    isa department, has name "開発部";
  $x isa project, has name "X";
  $y isa project, has name "Y";
  department-hierarchy (parent: $hq, child: $sales1);
  department-hierarchy (parent: $hq, child: $sales2);
  membership (member: $yamada, unit: $sales1);
  membership (member: $sato,   unit: $sales1);
  membership (member: $suzuki, unit: $sales2);
  membership (member: $tanaka, unit: $dev);
  assignment (assignee: $yamada, project: $x), has role-name "leader", has since 2026-04-01;
  assignment (assignee: $sato,   project: $x), has role-name "member", has since 2026-04-15;
  assignment (assignee: $suzuki, project: $y), has role-name "leader", has since 2026-05-01;
```

## 13.3 関数で推論する

TypeDB 3.x では、推論のルールを**関数**（`fun`）として書きます。関数はスキーマの一部としてデータベースに登録され、問い合わせの中で呼び出せます。再帰も否定も使えます。

```typeql
define
  # 部署 $d の配下の部署（推移的）
  fun sub_departments($d: department) -> { department }:
  match
    { department-hierarchy (parent: $d, child: $c); } or
    { department-hierarchy (parent: $d, child: $m); let $c in sub_departments($m); };
  return { $c };

  # リーダー $l が承認できる社員
  fun can_approve($l: employee) -> { employee }:
  match
    $a isa assignment, links (assignee: $l, project: $p), has role-name "leader";
    assignment (assignee: $m, project: $p);
    not { $m is $l; };
  return { $m };
```

関数は SQL のビューに近いものですが、引数をとれる、再帰できる、否定を使える、問い合わせの中で組み合わせられる、という点でルールとして使いやすくなっています。

## 13.4 TypeQL で問い合わせる

### Q1: 営業本部（配下を含む）に所属する社員

```typeql
match
  $hq isa department, has name "営業本部";
  { $d is $hq; } or { let $d in sub_departments($hq); };
  membership (member: $e, unit: $d);
  $e isa employee, has name $n;      # 正社員・契約社員も自動的に含まれる
fetch { "name": $n };
```

### Q2: リーダーが承認できる社員

```typeql
match
  $l isa employee, has name $ln;
  let $m in can_approve($l);
  $m has name $mn;
fetch { "leader": $ln, "member": $mn };
```

### Q3: どのプロジェクトにも割り当てられていない社員

```typeql
match
  $e isa employee, has name $n;
  not { assignment (assignee: $e); };
fetch { "name": $n };
```

## 13.5 否定と層化

TypeDB の関数は**層化否定**（第5章）に対応しています。否定の中で呼ぶ関数が、自分自身を（直接・間接に）否定の中で呼ばないことが条件です。このリポジトリでは、法律の「原則 → 例外 → 例外の例外」を、この性質を使って関数の連鎖として表しています（第25章）。

```typeql
# 例外が成り立たなければ、原則が成り立つ
fun holds_principle($c: claim) -> { claim }:
match
  let $y in conditions_of_principle($c);
  not { let $z in holds_exception($c); };
return { $c };
```

## 13.6 実際に使って分かったこと

このリポジトリで TypeDB 3.13 を使ったときに分かった点です（詳しくは第25章と docs/proposal/07・08）。

| 事項 | 内容 |
|------|------|
| 型の検査が厳しい | 間違いを早く見つけられる反面、クエリの書き方に慣れが要る |
| 引数のない関数を否定の中で呼ぶと遅い | 対象ごとに引数で渡す形にしたら、8 分半が 19 秒になった |
| `or` の分岐の中で否定と比較を組み合わせられない | 否定を別の関数に分けて回避した |
| 属性の多重度の既定は「0 か 1」 | 複数持たせたい属性は `@card(0..)` と書く |

## 13.7 得意なことと苦手なこと

| 得意 | 苦手 |
|------|------|
| n 項関係・ロール・関係の属性をそのまま書ける | 標準化された仕様ではない（TypeDB 独自） |
| エンティティ・関係・属性すべての継承 | 利用者・情報が RDF や Neo4j より少ない |
| 強い型検査で誤ったクエリやデータを防げる | スキーマを先に書く必要があり、試行錯誤の初期は手間 |
| 関数で再帰・層化否定を含むルールを書ける | バージョン（2.x のルール → 3.x の関数）で仕様が大きく変わった |

## まとめ

- TypeDB はエンティティ・リレーション・属性の 3 種類の型でデータを表し、関係は最初から n 項でロールを持つ
- 継承と強い型検査があり、関数で再帰・否定を含む推論を書ける
- 第3章〜第5章の考え方を、ほぼそのまま書けるのが強み。標準化されていない点が弱み

| 観点 | TypeDB / TypeQL |
|------|----------------|
| スキーマ | 必須。型・ロール・属性の所有を厳密に検査 |
| 継承 | エンティティ・リレーション・属性すべてにある |
| n 項関係 | そのまま書ける（ロールつき） |
| 推移的な関係 | 再帰関数 |
| ルール | 関数（再帰・層化否定） |
| 否定 | 閉世界（`not`）。関数では層化が条件 |
| 標準化 | 独自仕様 |
