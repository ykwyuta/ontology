# 4. 推奨構成の設計案

[03](03-modeling-approaches.md) で推奨したハイブリッド構成を、TypeQL（TypeDB 3.x）のスキーマと関数で具体化します。例題には、**売買代金請求に対する錯誤取消の抗弁（民法555条・95条）**を使います。

> 注: この節の TypeQL は TypeDB CE 3.13.6 で構文・型の検査を通り、4.5 の例題で期待どおりの結果が出ることを確認しました（[06](06-decisions.md#実機検証の結果フェーズ1の一部を前倒し)、[scripts/verify_proposal_typeql.py](../../scripts/verify_proposal_typeql.py)）。

## 4.1 条文層

```typeql
define
  # --- 属性 ---
  attribute law-id, value string;                 # e-Gov 法令ID 例: "129AC0000000089"（民法）
  attribute law-title, value string;
  attribute law-num, value string;                # 法令番号 例: "明治二十九年法律第八十九号"
  attribute law-type, value string
    @values("constitution", "treaty", "act", "cabinet-order",
            "ministerial-ordinance", "rule", "local-ordinance");
  attribute provision-path, value string;         # 例: "129AC0000000089/a95/p3/i1"（95条3項1号）
  attribute provision-num, value string;          # 枝番号のため文字列: "95", "3_2"
  attribute caption, value string;                # 見出し 例: "（錯誤）"
  attribute sentence-function, value string @values("main", "proviso", "former", "latter");
  attribute body-text, value string;
  attribute valid-from, value date;
  attribute valid-to, value date;
  attribute reference-kind, value string
    @values("refer", "apply-mutatis-mutandis", "read-as", "exclude", "notwithstanding");

  # --- 法令と規定単位 ---
  entity law,
    owns law-id @key, owns law-title, owns law-num, owns law-type,
    plays containment:container;

  entity provision @abstract,
    owns provision-path @key, owns provision-num, owns caption,
    plays containment:container, plays containment:part,
    plays provision-version:provision,
    plays cross-reference:citing, plays cross-reference:cited,
    plays norm-source:source;
  entity grouping sub provision;                  # 編・章・節・款・目
  entity article sub provision;                   # 条
  entity paragraph sub provision;                 # 項
  entity item sub provision;                      # 号・号の細分

  # 時点ごとの文言（溶け込み後の版）
  entity text-version,
    owns body-text, owns sentence-function, owns valid-from, owns valid-to,
    plays provision-version:version;

  relation containment, relates container, relates part;
  relation provision-version, relates provision, relates version;
  relation cross-reference, relates citing, relates cited, owns reference-kind;
```

準用の連鎖のような推移的な参照は、再帰関数でたどれます。参照する側からたどる関数と、参照される側からたどる関数（影響分析用）の両方を用意します。参照は条だけでなく項・号や編章節（「この節の規定は…準用する」）にも張られるので、包含関係を上下にたどる関数も使います。

```typeql
define
  fun referenced_transitively($p: provision) -> { provision }:
  match
    { cross-reference (citing: $p, cited: $q); } or
    { cross-reference (citing: $p, cited: $r); let $q in referenced_transitively($r); };
  return { $q };

  fun citing_transitively($p: provision) -> { provision }:
  match
    { cross-reference (citing: $q, cited: $p); } or
    { cross-reference (citing: $r, cited: $p); let $q in citing_transitively($r); };
  return { $q };

  fun parts_transitively($p: provision) -> { provision }:
  match
    { containment (container: $p, part: $q); } or
    { containment (container: $p, part: $r); let $q in parts_transitively($r); };
  return { $q };

  fun containers_transitively($p: provision) -> { provision }:
  match
    { containment (container: $q, part: $p); $q isa provision; } or
    { containment (container: $r, part: $p); $r isa provision; let $q in containers_transitively($r); };
  return { $q };
```

実装では、文言の版と参照に有効期間（`valid-from` / `valid-to`）を持たせ、時点を指定してたどる関数（`text_at`、`referenced_at`、`citing_at`）も定義しています（[schema/01-provisions.tql](../../schema/01-provisions.tql)、[07](07-phase1-results.md)）。

## 4.2 規範層

規範の正本です。要件を AND/OR の木で表し、例外関係・根拠・見解・有効期間を持たせます。

```typeql
define
  attribute norm-id, value string;                # 例: "N95-3"
  attribute norm-label, value string;
  attribute effect-code, value string;            # 例: "price-claim", "cancellation-by-mistake"
  attribute effect-category, value string
    @values("arising", "impeding", "extinguishing", "blocking");  # 発生・障害・消滅・阻止
  attribute pleading-layer, value integer;        # 0 請求原因, 1 抗弁, 2 再抗弁, 3 再々抗弁 ...
  attribute stance, value string;                 # "判例", "通説", "有力説:○○" など
  attribute fact-code, value string;              # 要件事実の識別子 例: "N95-3.gross-negligence"
  attribute connective, value string @values("and", "or");
  attribute evaluative, value boolean;            # 規範的要件か（「重大な過失」など）
  attribute burden-side, value string @values("claimant", "respondent");
  attribute function-name, value string;          # コンパイラが生成した関数名
  attribute override-ground, value string
    @values("lex-superior", "lex-specialis", "lex-posterior", "explicit");
  attribute case-number, value string;
  attribute court, value string;
  attribute decision-date, value date;
  attribute grand-bench, value boolean;

  entity norm,
    owns norm-id @key, owns norm-label, owns effect-code, owns effect-category,
    owns pleading-layer, owns stance, owns valid-from, owns valid-to, owns function-name,
    plays norm-condition:norm, plays norm-source:norm,
    plays exception:base, plays exception:exception,
    plays overrides:superior, plays overrides:inferior,
    plays derivation:applied-norm;

  # 要件の木
  entity condition @abstract,
    plays norm-condition:root, plays condition-part:whole, plays condition-part:part;
  entity atomic-condition sub condition,
    owns fact-code, owns evaluative, owns burden-side;
  entity compound-condition sub condition,
    owns connective;

  relation norm-condition, relates norm, relates root;
  relation condition-part, relates whole, relates part;

  # 根拠（条文または判例）
  entity precedent,
    owns case-number @key, owns court, owns decision-date, owns grand-bench,
    plays norm-source:source;
  relation norm-source, relates norm, relates source;

  # 原則・例外と優先関係
  relation exception, relates base, relates exception;
  relation overrides, relates superior, relates inferior, owns override-ground;
```

要件の木から末端の要件事実を集める関数です。「この規範で立証が必要な事実」の列挙や、不足事実の検出に使います。

```typeql
define
  fun subconditions($c: condition) -> { condition }:
  match
    { condition-part (whole: $c, part: $x); } or
    { condition-part (whole: $c, part: $y); let $x in subconditions($y); };
  return { $x };

  fun required_facts($n: norm) -> { atomic-condition }:
  match
    norm-condition (norm: $n, root: $root);
    { $a is $root; } or { let $a in subconditions($root); };
    $a isa atomic-condition;
  return { $a };
```

### 規範データの例（民法95条）

```typeql
insert
  # 再抗弁: 表意者の重大な過失（95条3項柱書）
  $n3 isa norm, has norm-id "N95-3",
      has norm-label "表意者の重過失による錯誤取消の排除",
      has effect-code "bar-mistake-cancellation", has effect-category "impeding",
      has pleading-layer 2, has stance "条文", has valid-from 2020-04-01,
      has function-name "mistake_rebuttal";
  $c3 isa atomic-condition, has fact-code "N95-3.gross-negligence",
      has evaluative true, has burden-side "claimant";
  norm-condition (norm: $n3, root: $c3);

  # 再々抗弁: 相手方の悪意・重過失（1号）／共通錯誤（2号）
  $n31 isa norm, has norm-id "N95-3-exc",
      has norm-label "相手方の悪意・重過失又は共通錯誤",
      has effect-code "lift-bar", has effect-category "impeding",
      has pleading-layer 3, has stance "条文", has valid-from 2020-04-01,
      has function-name "mistake_rerebuttal";
  $or isa compound-condition, has connective "or";
  $k1 isa atomic-condition, has fact-code "N95-3-1.counterparty-knew-or-gross-negligence",
      has evaluative true, has burden-side "respondent";
  $k2 isa atomic-condition, has fact-code "N95-3-2.common-mistake",
      has evaluative false, has burden-side "respondent";
  norm-condition (norm: $n31, root: $or);
  condition-part (whole: $or, part: $k1);
  condition-part (whole: $or, part: $k2);

  exception (base: $n3, exception: $n31);
```

根拠条文との対応（`norm-source`）は、条文層の `provision-path` を照合して張ります。

## 4.3 事案層

```typeql
define
  attribute case-id, value string;
  attribute party-name, value string;
  attribute price, value integer;
  attribute concluded-on, value date;
  attribute declared-on, value date;
  attribute procedure-type, value string @values("civil", "criminal", "administrative");
  attribute proof-status, value string
    @values("admitted", "proven", "unclear", "disproven");   # 自白・証明済・真偽不明・否定

  entity case-file,
    owns case-id @key, owns procedure-type,
    plays case-membership:case;
  relation case-membership, relates case, relates member;

  entity party, owns party-name,
    plays sales-contract:seller, plays sales-contract:buyer,
    plays contract-declaration:declarant,
    plays case-membership:member, plays fact-finding:subject;

  entity declaration-of-intent, owns declared-on,
    plays contract-declaration:declaration,
    plays case-membership:member, plays fact-finding:subject;

  relation sales-contract,
    relates seller, relates buyer, owns price, owns concluded-on,
    plays contract-declaration:contract,
    plays case-membership:member, plays fact-finding:subject,
    plays derivation:subject;

  relation contract-declaration, relates contract, relates declaration, relates declarant;

  # 要件事実の認定。規範層の fact-code と同じ属性値で対応づける
  relation fact-finding,
    relates subject, owns fact-code, owns proof-status,
    plays case-membership:member;

  # 推論結果の実体化（導出記録）
  attribute derived-at, value datetime;
  relation derivation,
    relates subject, relates applied-norm, owns effect-code, owns stance, owns derived-at;
```

「証明された」の判定は、手続の種類によって真偽不明の扱いを切り替えられるよう、1 つの関数に集約します（民事の例）。

```typeql
define
  fun established() -> { fact-finding }:
  match
    $f isa fact-finding, has proof-status $s;
    { $s == "admitted"; } or { $s == "proven"; };
  return { $f };
```

## 4.4 推論層: コンパイラが生成する関数

> 実装では、推論の単位を訴訟物（`claim`）に統一し、関数は訴訟物を引数にとる形にしました（引数のない形は否定の中で遅くなるため）。詳しくは [08](08-phase2-results.md#82-提案からの変更点)。この節は当初の設計として残しています。

コンパイラは規範層から、`pleading-layer` と `exception` 関係に沿って次の関数を生成します。各関数は自分より深い層の関数だけを否定の中で呼ぶので、層化否定の条件を満たします。

```typeql
define
  # 層3 再々抗弁: 95条3項1号・2号
  fun mistake_rerebuttal() -> { declaration-of-intent }:
  match
    $d isa declaration-of-intent;
    { $f1 isa fact-finding, links (subject: $d),
          has fact-code "N95-3-1.counterparty-knew-or-gross-negligence";
      let $f1 in established(); }
    or
    { $f2 isa fact-finding, links (subject: $d), has fact-code "N95-3-2.common-mistake";
      let $f2 in established(); };
  return { $d };

  # 層2 再抗弁: 95条3項柱書（表意者の重過失）
  fun mistake_rebuttal() -> { declaration-of-intent }:
  match
    $d isa declaration-of-intent;
    $f isa fact-finding, links (subject: $d), has fact-code "N95-3.gross-negligence";
    let $f in established();
    not { let $d in mistake_rerebuttal(); };
  return { $d };

  # 層1の要件部分: 95条1項（重要な錯誤）＋1号 表示の錯誤 / 2号・2項 表示された動機の錯誤
  fun mistake_ground() -> { declaration-of-intent }:
  match
    $d isa declaration-of-intent, has declared-on $t;
    $t >= 2020-04-01;                                    # 改正後の95条の適用範囲（附則6条1項）
    $m isa fact-finding, links (subject: $d), has fact-code "N95-1.material";
    let $m in established();
    { $e isa fact-finding, links (subject: $d), has fact-code "N95-1-1.mistake-in-expression";
      let $e in established(); }
    or
    { $v isa fact-finding, links (subject: $d), has fact-code "N95-1-2.mistake-in-motive";
      let $v in established();
      $i isa fact-finding, links (subject: $d), has fact-code "N95-2.motive-indicated";
      let $i in established(); };
  return { $d };

  # 層1 抗弁: 錯誤取消（95条1項, 121条）＋取消の意思表示（123条）
  fun defence_mistake() -> { sales-contract }:
  match
    $c isa sales-contract, links (buyer: $p);
    contract-declaration (contract: $c, declaration: $d, declarant: $p);
    let $d in mistake_ground();
    $x isa fact-finding, links (subject: $d), has fact-code "N123.cancellation-declared";
    let $x in established();
    not { let $d in mistake_rebuttal(); };
  return { $c };

  # 層0 請求原因: 売買契約の締結（555条）
  fun price_claim_ground() -> { sales-contract }:
  match
    $c isa sales-contract;
    $f isa fact-finding, links (subject: $c), has fact-code "N555.contract-concluded";
    let $f in established();
  return { $c };

  # 結論: 請求原因が認められ、どの抗弁も成立しない
  fun price_claim_granted() -> { sales-contract }:
  match
    let $c in price_claim_ground();
    not { let $c in defence_mistake(); };
    not { let $c in defence_payment(); };                # 弁済（473条）
    not { let $c in defence_prescription(); };           # 消滅時効（166条, 145条）
  return { $c };
```

（`defence_payment` と `defence_prescription` も同じパターンで生成します。）

**時点による切替**: 2020年3月31日以前の意思表示には、旧95条（要素の錯誤 → 無効、表意者に重過失があれば無効を主張できない）から生成した `mistake_ground_pre2020` などを `declared-on < 2020-04-01` の条件で併置し、`defence_mistake` でどちらかが成立すればよい形にします。

**見解による切替**: 見解ごとに異なる規範（例: 動機の錯誤の要件について判例と有力説）がある場合は、見解ごとに関数を生成します（`mistake_ground__hanrei` など）。結論の関数も見解の組み合わせごとに生成するか、外側のクエリで選びます。

## 4.5 クエリの例

### 例題の事案

2024年5月、買主 Y が売主 X から絵画を 300万円で買った（改正後の95条が適用される）。Y は有名画家の真作と信じ、その動機を X に表示していたが、実際は贋作だった。Y は錯誤を理由に取り消した。

| 事実 | 証明状態 |
|------|---------|
| 売買契約の締結（555条） | 自白 |
| 重要な錯誤（95条1項）／動機の錯誤（1項2号）／動機の表示（2項） | 証明済 |
| 取消の意思表示（123条） | 自白 |
| Y の重大な過失（95条3項） | 証明済 |
| X が Y の錯誤を知っていた（95条3項1号） | **真偽不明** |

### Q1. 結論: 代金支払請求は認められるか

```typeql
match
  $case isa case-file, has case-id "2026-demo-001";
  case-membership (case: $case, member: $c);
  let $c in price_claim_granted();
  $c isa sales-contract, links (seller: $s, buyer: $b), has price $amount;
  $s has party-name $sn; $b has party-name $bn;
fetch { "seller": $sn, "buyer": $bn, "price": $amount };
```

→ 請求は認められます。重過失の再抗弁が成立し、それを覆す再々抗弁（X の悪意）が真偽不明のため、証明責任を負う Y の不利益に扱われるからです。

### Q2. 不足事実: 結論を変えるには、誰が何を立証すればよいか

```typeql
match
  $case isa case-file, has case-id "2026-demo-001";
  case-membership (case: $case, member: $f);
  $f isa fact-finding, has fact-code $code, has proof-status "unclear";
  $a isa atomic-condition, has fact-code $code, has burden-side $side;
  norm-condition (norm: $n, root: $root);
  { $a is $root; } or { let $a in subconditions($root); };
  $n has norm-id $nid, has norm-label $label;
fetch { "norm": $nid, "label": $label, "fact": $code, "burden": $side };
```

→ `N95-3-exc / N95-3-1.counterparty-knew-or-gross-negligence / respondent`。つまり、Y（被告）が「X が Y の錯誤を知っていた、または重大な過失で知らなかった」ことを立証すれば、結論が変わる可能性があります。

### Q3. 根拠: 結論はどの条文・判例に基づくか

実体化パスで書き戻した `derivation` を条文層までたどります。

```typeql
match
  $dv isa derivation, links (subject: $c, applied-norm: $n);
  norm-source (norm: $n, source: $src);
  $n has norm-id $nid;
  $src has provision-path $path;
fetch { "norm": $nid, "source": $path };
```

### Q4. 影響分析: 95条が改正されたら、どの事案の結論が変わりうるか

95条を**参照している側**の規定をたどります（当初の案では `referenced_transitively` を使っており、95条が参照している側をたどる逆向きの誤りでした。フェーズ1の実装で修正）。

```typeql
match
  $p isa article, has provision-path "129AC0000000089/a95";
  # 95条とその項・号、およびそれを含む節・章（「この節の規定は…」で参照されうる）
  { $t is $p; } or { let $t in parts_transitively($p); } or { let $t in containers_transitively($p); };
  # それらを根拠とする規範と、それらを（準用などで推移的に）参照する規定を根拠とする規範
  { norm-source (norm: $n, source: $t); } or
  { let $q in citing_transitively($t); norm-source (norm: $n, source: $q); };
  $dv isa derivation, links (subject: $c, applied-norm: $n);
  case-membership (case: $case, member: $c);
  $case has case-id $cid;
  $n has norm-id $nid;
fetch { "case": $cid, "norm": $nid };
```

## 4.6 実体化パス（導出記録の書き戻し）

TypeDB 3.x の関数はデータを書かないため、アプリケーション（コンパイラと同じコンポーネント）が、評価の都度、次のような書き込みを実行します。

```typeql
match
  let $c in price_claim_granted();
  $n isa norm, has norm-id "N555";
insert
  $dv isa derivation, links (subject: $c, applied-norm: $n),
      has effect-code "price-claim", has stance "判例", has derived-at 2026-10-02T00:00:00;
```

規範ごと（抗弁が退けられた理由を含む）に同様の書き込みを行えば、結論に至った論証の木がグラフとして残ります。規範・事実・見解・時点のどれかが変われば、導出記録を無効化して再計算します。

## 4.7 コンパイラの責務

| 入力（規範層） | 出力（推論層） |
|---------------|---------------|
| `norm` と要件の木（AND→パターンの連結, OR→`or` 節） | 規範ごとのストリーム関数 |
| `exception` 関係 | 例外関数を呼ぶ `not { let ... in ...; }` |
| `pleading-layer` と `exception` の深さ | 関数の呼び出し順序（層化の検査を含む。循環があればエラーにして規範層の修正を求める） |
| `valid-from` / `valid-to` | 事実の時点（`declared-on` など）に対する条件 |
| `stance` | 見解ごとに関数を生成し分ける |
| 「みなす」規範 | 事実を確定させる関数（`established()` の和集合に加える） |
| 「推定する」規範 | 前提事実から推定事実を導き、反対事実の証明（`disproven`）で覆る関数 |
| 主体の対応（「表意者」= 買主など） | ドメインの役割（`buyer`, `declarant`）への束縛。規範層に役割の対応表を持たせる |

最後の「主体の対応」は、規範を一階の規則として書くために必要な情報です。PROLEG のように、規範の述語の引数と事案の役割の対応を規範層に持たせ、コンパイラが TypeQL の変数に展開します。
