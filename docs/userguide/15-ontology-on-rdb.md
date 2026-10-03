# 第15章 RDB でオントロジー的に設計する

ここまで専用のデータベースを見てきましたが、オントロジーの考え方は RDB でも生かせます。既存の資産と運用ノウハウがある RDB を使い続けながら、意味をはっきりさせる設計を考えます。

## 15.1 例題をテーブルで書く

```sql
CREATE TABLE department (
  id        INT PRIMARY KEY,
  name      VARCHAR(100) NOT NULL,
  parent_id INT REFERENCES department(id)          -- 上位部署（階層）
);

CREATE TABLE employee (
  id      INT PRIMARY KEY,
  name    VARCHAR(100) NOT NULL,
  kind    VARCHAR(20) NOT NULL CHECK (kind IN ('regular', 'contract')),   -- 継承の種別
  dept_id INT NOT NULL REFERENCES department(id)
);

CREATE TABLE regular_employee  (id INT PRIMARY KEY REFERENCES employee(id), grade INT);
CREATE TABLE contract_employee (id INT PRIMARY KEY REFERENCES employee(id), contract_end DATE);

CREATE TABLE project (id INT PRIMARY KEY, name VARCHAR(100) NOT NULL);

CREATE TABLE assignment (                                -- n 項の関係 = 中間テーブル
  employee_id INT  NOT NULL REFERENCES employee(id),
  project_id  INT  NOT NULL REFERENCES project(id),
  role        VARCHAR(20) NOT NULL CHECK (role IN ('leader', 'member')),
  since       DATE NOT NULL,
  PRIMARY KEY (employee_id, project_id)
);
```

## 15.2 継承の 3 つの表し方

第2章で触れた、継承をテーブルで表す 3 つの方法です（Martin Fowler の『エンタープライズアプリケーションアーキテクチャパターン』の分類）。

| 方法 | テーブル | 「社員全員」の検索 | 子クラス固有の列 | 向いている場合 |
|------|---------|-----------------|---------------|-------------|
| シングルテーブル継承 | `employee` 1 つ（種別列 + 全子クラスの列） | 簡単 | NULL だらけになる | 子クラスの違いが小さい |
| クラステーブル継承 | 親 `employee` + 子 `regular_employee` など | 親テーブルだけで可能 | 子テーブルに素直に置ける | 意味をきちんと表したい（上の例はこれ） |
| 具象テーブル継承 | 子ごとに独立したテーブル | UNION が必要 | 素直に置ける | 子クラスどうしをまとめて扱わない |

オントロジーの考え方に一番近いのは**クラステーブル継承**です。親テーブルが「社員であること」、子テーブルが「正社員でもあること」を表します。

## 15.3 推移的な関係: 再帰 CTE

### Q1: 営業本部（配下を含む）に所属する社員

```sql
WITH RECURSIVE under_hq(id) AS (
  SELECT id FROM department WHERE name = '営業本部'
  UNION ALL
  SELECT d.id FROM department d JOIN under_hq u ON d.parent_id = u.id
)
SELECT e.name
FROM employee e JOIN under_hq u ON e.dept_id = u.id;
```

`WITH RECURSIVE` は SQL 標準で、PostgreSQL・MySQL 8・Oracle・SQL Server（`RECURSIVE` は省略）などで使えます。何段の階層でもたどれます。

## 15.4 ルールはビューで書く

### Q2: リーダーが承認できる社員

```sql
CREATE VIEW can_approve AS
SELECT l.employee_id AS leader_id, m.employee_id AS member_id
FROM assignment l
JOIN assignment m ON m.project_id = l.project_id AND m.employee_id <> l.employee_id
WHERE l.role = 'leader';
```

ビューにしておけば、ルールに名前が付き、他のクエリから再利用できます。ビューの上にビューを重ねれば、ルールの組み合わせ（第4章）も表せます。

### Q3: どのプロジェクトにも割り当てられていない社員

```sql
SELECT e.name FROM employee e
WHERE NOT EXISTS (SELECT 1 FROM assignment a WHERE a.employee_id = e.id);
```

## 15.5 避けたい設計: なんでも入る EAV

「将来どんな属性が増えても対応できるように」と、次のような汎用テーブルを作りたくなることがあります。

```sql
-- Entity-Attribute-Value（EAV）
CREATE TABLE fact (
  entity_id   INT,
  attribute   VARCHAR(100),
  value       VARCHAR(1000)
);
```

一見 RDF の三つ組（第11章）に似ていて、オントロジー的に見えます。しかし RDB でこれをやると、

- 型がすべて文字列になり、日付や数値の比較・制約が効かない
- 外部キー制約が使えず、存在しない相手を指してもわからない
- 1 つのモノの情報を取り出すのに、属性の数だけ自己結合が要る
- どんな属性があるかがデータを見ないとわからない（スキーマが消える）

という問題が出ます。RDF が三つ組でうまくいくのは、URI・データ型・スキーマ（RDFS/OWL/SHACL）・専用の索引と問い合わせ言語がセットになっているからです。**三つ組の形だけを RDB に持ち込むのは避けましょう。** 属性が頻繁に増えるなら、JSON 型の列に入れて CHECK 制約や JSON スキーマで検証するほうがましです。

## 15.6 意味をテーブル定義の外に書き出す

RDB でオントロジーの考え方を生かすコツは、**意味の情報を、テーブル定義とは別に、機械が読める形で持つ**ことです。

| 書き出すもの | 例 |
|------------|-----|
| 概念の定義 | 「顧客 = 受注契約を 1 件以上締結した法人または個人」 |
| テーブル・列と概念の対応 | `customer` テーブル = 概念「顧客」、`employee.kind = 'regular'` = 概念「正社員」 |
| 関係の性質 | `department.parent_id` は推移的な関係「配下である」 |
| ルール | `can_approve` ビュー = ルール「リーダーは同じプロジェクトのメンバーを承認できる」 |

データカタログ製品や、テーブルコメント、YAML の定義ファイルなどで持ち、ER 図・ビュー・ドキュメントをそこから生成すると、意味と実装がずれにくくなります。このリポジトリでも、法律のルール（規範）は YAML に書き、そこから TypeDB の関数を生成しています（第24章）。同じことは RDB のビューに対してもできます。

## 15.7 RDB とグラフの橋渡し

RDB の上でグラフ的な問い合わせをする手段も増えています。

| 手段 | 内容 |
|------|------|
| SQL/PGQ | SQL:2023 で標準化された、テーブルをプロパティグラフとして問い合わせる構文（`GRAPH_TABLE`）。対応する製品が増えつつある |
| PostgreSQL の拡張 | Apache AGE（Cypher で問い合わせる）など |
| 仮想ナレッジグラフ | RDB のテーブルを RDF に対応づけ（R2RML という W3C 標準）、SPARQL で問い合わせる。データは RDB に置いたまま（Ontop などの製品） |

既存の RDB を移行せずに、意味の層を上に重ねる構成（第7章）は、これらの手段で実現できます。

## 15.8 得意なことと苦手なこと

| 得意 | 苦手 |
|------|------|
| 既存資産・運用ノウハウ・人材がそろっている | 継承・意味をテーブル定義に表せない |
| トランザクション・集計・性能が成熟している | 推移的な関係やルールの組み合わせが書きにくい |
| 制約（主キー・外部キー・CHECK）が強い | 関係の種類が増えるとテーブルと結合が増える |
| SQL/PGQ・仮想ナレッジグラフで橋渡しできる | スキーマ変更のコストが高い |

## まとめ

- RDB でも、クラステーブル継承・中間テーブル・再帰 CTE・ビューで、オントロジーの考え方の多くを表せる
- 汎用の EAV テーブルは避ける
- 意味の情報を、テーブル定義とは別に機械可読な形で持ち、実装をそこから生成するとずれにくい
- SQL/PGQ や仮想ナレッジグラフで、RDB のデータをグラフとして問い合わせることもできる

| 観点 | RDB |
|------|-----|
| スキーマ | 必須。制約が強い。意味は外に書く |
| 継承 | 3 通りの表し方（クラステーブル継承が近い） |
| n 項関係 | 中間テーブル |
| 推移的な関係 | 再帰 CTE |
| ルール | ビュー（再帰ビューを含む） |
| 否定 | 閉世界（`NOT EXISTS`） |
| 標準化 | SQL 標準。SQL/PGQ（2023） |
