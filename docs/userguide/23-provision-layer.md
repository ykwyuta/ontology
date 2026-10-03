# 第23章 条文層: 法令データの取り込み

条文層は、民法の条文を、構造と改正の履歴を保ったまま TypeDB に入れる層です。ここでは、法令データの形、ID の付け方、版の扱い、条文間の参照の抽出を見ていきます。

## 23.1 元データ: e-Gov 法令 API

e-Gov 法令検索は、法令を**法令標準 XML** で公開しており、法令 API（バージョン 2）で取得できます。

| API | 返すもの |
|-----|---------|
| `/api/2/law_revisions/{法令ID}` | 改正履歴の一覧（版ごとの ID、施行日、状態） |
| `/api/2/law_data/{法令ID または 版ID}` | 法令の本文（XML。JSON の中に base64 で入っている） |

民法の法令 ID は `129AC0000000089` です。2016-10-13 以降の版が取得できます。XML の中身は、次のような木構造です。

```xml
<Article Num="95">
  <ArticleCaption>（錯誤）</ArticleCaption>
  <Paragraph Num="3">
    <ParagraphSentence>
      <Sentence>錯誤が表意者の重大な過失によるものであった場合には、…</Sentence>
    </ParagraphSentence>
    <Item Num="1">
      <ItemSentence><Sentence>相手方が表意者に錯誤があることを知り、…</Sentence></ItemSentence>
    </Item>
  </Paragraph>
</Article>
```

`src/legal_onto/egov.py` が API を呼び、取得した XML を `data/cache/egov/` に保存します。`src/legal_onto/lawxml.py` が XML を規定の木に変換します。

## 23.2 ID の付け方

条・項・号には、XML の `Num` 属性から**パス形式の ID**を付けます（第6章の共通 ID）。

| 単位 | ID | 例 |
|------|-----|-----|
| 条 | `{法令ID}/a{Num}` | `129AC0000000089/a98_2`（98 条の 2） |
| 項・号 | `…/p{Num}/i{Num}` | `129AC0000000089/a95/p3/i1`（95 条 3 項 1 号） |
| 編・章・節 | `{法令ID}/pt{Num}/ch{Num}/se{Num}` | `129AC0000000089/pt2/ch3/se3` |
| 附則 | `{法令ID}/sp:{改正法令の番号}` | `…/sp:平成二九年六月二日法律第四四号/a6/p1` |

**条の ID に編・章・節を含めていない**のがポイントです。改正で条が別の章に移っても、ID が変わらないようにするためです。章との関係は、包含関係（`containment`）として別に持ちます。RDB で「自然キーに変わりうる情報を含めない」のと同じ考え方です。

## 23.3 スキーマ

```typeql
entity provision @abstract,
  owns provision-path @key, owns provision-num, owns caption,
  plays containment:container, plays containment:part,
  plays provision-version:provision,
  plays cross-reference:citing, plays cross-reference:cited;
entity grouping sub provision;     # 編・章・節・款・目・附則
entity article sub provision;      # 条
entity paragraph sub provision;    # 項
entity item sub provision;         # 号

entity text-version,               # ある期間の文言（1 文ごと）
  owns body-text, owns sentence-function, owns sentence-num,
  owns valid-from, owns valid-to, ...;

relation containment, relates container, relates part;
relation provision-version, relates provision, relates version;
relation cross-reference, relates citing, relates cited,
  owns reference-kind, owns valid-from, owns valid-to, ...;
```

継承（第2章）で「条も項も号も規定の一種」と表し、「規定」で問い合わせればすべてが返るようにしています。

## 23.4 改正の版と有効期間

法令は改正されると、改正の内容が元の法令に溶け込んだ新しい版になります。同じ条でも、時点によって文言が違います。たとえば民法 95 条（錯誤）は、2020 年 4 月 1 日の改正で大きく変わりました。

| 時点 | 95 条の要旨 |
|------|-----------|
| 2020-03-31 まで | 要素に錯誤があれば無効。ただし重大な過失があれば表意者は無効を主張できない |
| 2020-04-01 から | 重要な錯誤があれば取り消せる。基礎事情の錯誤は表示が必要。重大な過失があれば取り消せない（例外あり） |

取り込みでは、施行日ごとに 1 つの版を取得し、**版を並べて比べて、内容が変わらない期間をまとめます**（`src/legal_onto/versions.py`）。各文言に「この日から有効（`valid-from`）」「この日から無効（`valid-to`、その日を含まない）」を付けます。

時点を指定して文言を引く関数は、次のように書けます。

```typeql
fun text_at($p: provision, $t: date) -> { text-version }:
match
  provision-version (provision: $p, version: $v);
  $v has valid-from $f; $f <= $t;
  not { $v has valid-to $e; $e <= $t; };
return { $v };
```

```bash
legal-onto text 129AC0000000089/a95 --at 2019-06-01   # 旧 95 条
legal-onto text 129AC0000000089/a95 --at 2024-05-10   # 新 95 条
```

## 23.5 条文間の参照を抽出する

条文には、他の条文への参照がたくさんあります。

- 「前項第二号の規定による」
- 「第九十六条第二項及び第三項」（「第三項」も 96 条の項）
- 「第六百四十四条から第六百五十条までの規定は、…について準用する」
- 「この節（第二百六十二条の二及び第二百六十二条の三を除く。）の規定は、…準用する」
- 附則の「新法第九十五条…の規定にかかわらず、なお従前の例による」

`src/legal_onto/refs.py` が、これらを規則で解析し、参照先の ID に変換します。参照の種類も、直後の言葉から判定します。

| 種類 | 判定の手がかり | 民法での件数（最新版） |
|------|-------------|------------------:|
| 準用 | 「…の規定は、…について準用する」 | 531 |
| にかかわらず | 「…の規定にかかわらず」 | 120 |
| 除く | 「…を除く」「…を除き」 | 24 |
| 読替え | 「…中「…」とあるのは」 | 19 |
| 参照 | それ以外 | 1,459 |

参照は推移的にたどれるので（第4章）、「95 条を参照している規定」「その規定を参照している規定」…と影響範囲を広げていけます。

```bash
legal-onto refs 129AC0000000089/a249 --reverse --at 2024-05-10 --with-containers
# → 263 条・264 条（「この節の規定は…準用する」で、249 条を含む節を参照）
```

## 23.6 取り込みの検証

取り込んだデータが正しいかは、元データと突き合わせて確かめました（第9章「データ品質」）。

- 5 つの版から無作為に選んだ 200 の規定で、DB から時点を指定して引いた文言が XML と一致
- 最新版で有効な文の数（3,175）が XML と一致
- 参照の抽出は、本則で解決できなかった表現が 1 件（他の法令を指すもので、解決しないのが正しい）

## 23.7 数字で見る条文層

| 項目 | 件数 |
|------|-----:|
| 取り込んだ版 | 27（2016-10-13〜2026-06-24） |
| 規定（編章節・条・項・号、附則を含む） | 4,509 |
| 文言の版 | 3,821（うち 2020-04-01 の債権法改正で 875） |
| 参照 | 2,376 |
| 取り込み時間 | 約 30 秒（XML をキャッシュ済みのとき） |

## まとめ

- e-Gov 法令 API の XML を、条・項・号の木として取り込み、変わらない ID を付ける
- 版を比べて文言に有効期間を付け、時点を指定して条文を引けるようにする
- 条文間の参照を規則で抽出し、種類（準用など）を付けて、影響範囲をたどれるようにする
- 取り込んだデータは元データと突き合わせて検証する
