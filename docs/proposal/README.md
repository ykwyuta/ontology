# 提案: TypeDB による日本法の知識表現と法的判断クエリ

日本の法体系を TypeDB 上に表現し、「この事実関係のもとで、この請求は認められるか」「その根拠は何か」「結論を変えるには何を立証すればよいか」といった法的判断を、クエリとして引き出せるようにするための提案です。

## 文書構成

| # | 文書 | 内容 |
|---|------|------|
| 1 | [01-japanese-legal-system.md](01-japanese-legal-system.md) | 調査: 日本の法体系（法源・法令の階層・適用原則・条文構造・法令用語・データ源） |
| 2 | [02-legal-reasoning.md](02-legal-reasoning.md) | 調査: 法的論法の構成（法的三段論法・法解釈・要件事実論・刑法の犯罪論体系・先行研究） |
| 3 | [03-modeling-approaches.md](03-modeling-approaches.md) | 方式の比較: TypeDB で表現・推論する 5 つの方式と推奨構成 |
| 4 | [04-schema-design.md](04-schema-design.md) | 推奨構成の設計案: TypeQL スキーマと関数の具体例（民法の売買代金請求と錯誤取消） |
| 5 | [05-roadmap.md](05-roadmap.md) | 段階的な進め方・検証方法・リスク |
| 6 | [06-decisions.md](06-decisions.md) | 決定事項（用途・分野・実行環境・レビュー体制）と設計への反映、実機検証の結果 |
| 7 | [07-phase1-results.md](07-phase1-results.md) | フェーズ1の結果: 民法の版つき取り込み、参照の抽出、TypeDB 3.13 で分かったこと |
| 8 | [08-phase2-results.md](08-phase2-results.md) | フェーズ2の結果: 規範（29件）、コンパイラ、事案の評価と報告 |

## 要旨

1. **日本法は「要件 → 効果」の条件付き規範と「原則 → 例外」の重なりでできている。** 条文の本文とただし書、「前項の規定にかかわらず」、民事訴訟での請求原因・抗弁・再抗弁という層構造（要件事実論）がその典型です。この構造は、論理プログラミングでいう**層化否定（stratified negation）**とよく対応します。
2. **TypeDB 3.x の関数（`fun`）は再帰・層化否定・テーブリングに対応しており、この層構造をそのまま書ける。** 「抗弁が成立しない限り請求原因から効果が生じる」は `not { let $x in defence(); }` で表せます。立証責任の考え方（真偽不明なら証明責任を負う側の不利益になる）も、否定を「失敗による否定」として扱う意味論と一致します。
3. **推奨構成は 4 層のハイブリッドです。**
   - **条文層**: e-Gov 法令API v2 の法令標準XMLを取り込み、法令・条・項・号・版（時点）・参照関係を保持する。
   - **規範層**: 要件・効果・例外関係・根拠条文・判例を**データとして**保持する。規範の唯一の正本はここに置く。
   - **推論層**: 規範層から TypeQL 関数を**自動生成（コンパイル）**し、事案の事実に適用する。
   - **事案層**: 当事者・事実・証明状態・評価（規範的要件）を保持する。推論結果と導出根拠は書き戻して、監査・説明に使う。
4. **最初は範囲を絞ってスモールスタートする。** 民法総則の意思表示（93〜98条の2）と売買（555条以下）・消滅時効から始め、PROLEG の規則や COLIEE のデータで検証します。

## 用語

| 用語 | 意味 |
|------|------|
| 規範 (norm) | 「要件を満たせば効果が生じる」という条件付きの法的命題。1 つの条文に複数含まれることもあり、判例から導かれることもある |
| 要件事実 | 法律効果の発生に直接必要な具体的事実 |
| 証明状態 | 事実が「自白」「証明済」「真偽不明」「否定」のどれにあるか |
| 層 (stratum) | 原則・例外・例外の例外という否定の入れ子の深さ |

## 主な参考資料

- e-Gov 法令API Version2 リリースのお知らせ: https://laws.e-gov.go.jp/file/法令APIバージョン2リリースのお知らせ.pdf
- 法令データの構造と XML（e-Gov 法令検索）: https://laws.e-gov.go.jp/docs/law-data-basic/8ebd8bc-law-structure-and-xml/
- 法令標準XMLスキーマ v3: https://elaws.e-gov.go.jp/file/XMLSchemaForJapaneseLaw_v3.pdf
- TypeDB: Functions vs rules: https://typedb.com/docs/typeql-reference/functions/functions-vs-rules/
- TypeDB: Negations: https://typedb.com/docs/typeql/patterns/negations
- TypeDB 3.0 Roadmap: https://typedb.com/blog/typedb-3-roadmap
- K. Satoh et al., "PROLEG: An Implementation of the Presupposed Ultimate Fact Theory of Japanese Civil Code": https://www.springerprofessional.de/proleg-an-implementation-of-the-presupposed-ultimate-fact-theory/3789286
- 国立情報学研究所 佐藤健 研究室の資料（PROLEG）: https://www.nii.ac.jp/event/upload/20230707-04_Satoh.pdf
