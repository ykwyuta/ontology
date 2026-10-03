# 付録C 参考資料

本書で触れた仕様・製品・事例の出典です。URL は 2026 年 10 月時点のもので、変わることがあります。

## 標準仕様

| 資料 | 内容 | 章 |
|------|------|----|
| W3C, RDF 1.1 Concepts and Abstract Syntax — https://www.w3.org/TR/rdf11-concepts/ | RDF の基本 | 11 |
| W3C, RDF 1.2 Concepts and Abstract Syntax — https://www.w3.org/TR/rdf12-concepts/ | 三つ組についての三つ組（triple terms）を含む次の版 | 11 |
| W3C, OWL 2 Web Ontology Language Document Overview — https://www.w3.org/TR/owl2-overview/ | OWL | 11 |
| W3C, SPARQL 1.1 Query Language — https://www.w3.org/TR/sparql11-query/ | SPARQL | 11 |
| W3C, Shapes Constraint Language (SHACL) — https://www.w3.org/TR/shacl/ | データの検証 | 11 |
| W3C, SKOS Simple Knowledge Organization System Reference — https://www.w3.org/TR/skos-reference/ | 分類体系・概念の対応 | 6 |
| W3C, PROV-O: The PROV Ontology — https://www.w3.org/TR/prov-o/ | データの来歴 | 6 |
| W3C, R2RML: RDB to RDF Mapping Language — https://www.w3.org/TR/r2rml/ | RDB と RDF の対応づけ | 15 |
| schema.org — https://schema.org/ | Web の構造化データの語彙 | 6, 8 |
| ISO/IEC 39075:2024 Information technology — Database languages — GQL | プロパティグラフの問い合わせ言語 | 12 |
| openCypher — https://opencypher.org/ | Cypher の公開仕様 | 12 |
| ISO/IEC 9075-16:2023 (SQL/PGQ) | SQL のプロパティグラフ問い合わせ | 15 |
| Basic Formal Ontology (BFO) — https://basic-formal-ontology.org/ | 上位オントロジー | 6 |

## 製品・処理系

| 資料 | 内容 | 章 |
|------|------|----|
| TypeDB Documentation — https://typedb.com/docs/ | TypeDB と TypeQL（関数、否定） | 13, 25 |
| Neo4j Cypher Manual — https://neo4j.com/docs/cypher-manual/current/ | Cypher | 12 |
| Soufflé — https://souffle-lang.github.io/ | Datalog の処理系 | 14 |
| Potassco (clingo) — https://potassco.org/ | ASP の処理系 | 14 |
| Apache Jena — https://jena.apache.org/ | RDF の処理系・トリプルストア | 11 |

## 事例

| 資料 | 内容 | 章 |
|------|------|----|
| SNOMED International — https://www.snomed.org/ | SNOMED CT | 8 |
| Gene Ontology — https://geneontology.org/ | Gene Ontology | 8 |
| EDM Council, FIBO — https://spec.edmcouncil.org/fibo/ | 金融のオントロジー | 8 |
| Brick Schema — https://brickschema.org/ | ビルの設備・計測点の語彙 | 8 |
| ISO 15926 Industrial automation systems and integration — Integration of life-cycle data for process plants including oil and gas production facilities | プラントのライフサイクルデータ | 8 |
| Google, "Introducing the Knowledge Graph: things, not strings" (2012) — https://blog.google/products/search/introducing-knowledge-graph-things-not/ | Google の Knowledge Graph | 8 |
| X. L. Dong et al., "AutoKnow: Self-Driving Knowledge Collection for Products of Thousands of Types", KDD 2020 | Amazon の商品知識グラフ | 8 |
| e-Gov 法令検索 — https://laws.e-gov.go.jp/ | 法令標準 XML、法令 API | 8, 23 |
| OASIS LegalDocML (Akoma Ntoso) — https://www.oasis-open.org/committees/legaldocml/ | 法令文書の XML 標準 | 8 |
| OASIS LegalRuleML — https://www.oasis-open.org/committees/legalruleml/ | 法的ルールの記述標準 | 8 |
| European Legislation Identifier (ELI) — https://eur-lex.europa.eu/eli-register/about.html | 欧州の法令 ID | 8 |

## 法律と論理

| 資料 | 内容 | 章 |
|------|------|----|
| K. Satoh et al., "PROLEG: An Implementation of the Presupposed Ultimate Fact Theory of Japanese Civil Code by PROLOG Technology" | PROLEG | 14, 24 |
| 国立情報学研究所 佐藤健 研究室の資料 — https://www.nii.ac.jp/event/upload/20230707-04_Satoh.pdf | PROLEG の解説 | 14 |
| M. J. Sergot et al., "The British Nationality Act as a Logic Program", Communications of the ACM, 1986 | 法律を論理プログラムで書いた古典的な研究 | 14 |
| 司法研修所編『紛争類型別の要件事実』（法曹会） | 要件事実論。このリポジトリの規範の典拠 | 24 |
| 民法（明治二十九年法律第八十九号）、民法の一部を改正する法律（平成二十九年法律第四十四号）附則 | 規範と経過措置の根拠 | 24 |

## AI

| 資料 | 内容 | 章 |
|------|------|----|
| D. Edge et al., "From Local to Global: A Graph RAG Approach to Query-Focused Summarization", arXiv:2404.16130 (2024) | Microsoft Research の GraphRAG | 19 |
| Model Context Protocol — https://modelcontextprotocol.io/ | AI とツール・データをつなぐ仕組み | 19 |
| Anthropic, Claude Code の公式ドキュメント | コーディングエージェント | 20, 27 |
| OpenAI, Codex の公式ドキュメント | コーディングエージェント | 20 |

## 書籍

| 資料 | 内容 | 章 |
|------|------|----|
| M. Fowler, *Patterns of Enterprise Application Architecture*, Addison-Wesley, 2002 | 継承をテーブルで表す 3 つのパターン | 15 |

## このリポジトリの文書

| 文書 | 内容 |
|------|------|
| [docs/proposal/](../proposal/README.md) | 提案書（調査、方式の比較、設計） |
| [docs/proposal/06-decisions.md](../proposal/06-decisions.md) | 決定事項と、専門家レビューの代替策 |
| [docs/proposal/07-phase1-results.md](../proposal/07-phase1-results.md) | フェーズ1（条文層）の結果 |
| [docs/proposal/08-phase2-results.md](../proposal/08-phase2-results.md) | フェーズ2（規範層とコンパイラ）の結果 |
| [norms/README.md](../../norms/README.md) | 規範の書式 |
