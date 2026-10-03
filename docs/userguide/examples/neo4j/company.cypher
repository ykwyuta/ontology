// 第12章の例題（社員・部署・プロジェクト）
// 実行: docker compose exec neo4j cypher-shell -f /examples/company.cypher

// やり直せるように、既存のデータを消す
MATCH (n) DETACH DELETE n;

// ノード（ラベルは複数付けられる）と関係（向きと属性を持つ）
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
       (sales1)-[:SUB_OF]->(hq),
       (sales2)-[:SUB_OF]->(hq),
       (yamada)-[:MEMBER_OF]->(sales1),
       (sato)-[:MEMBER_OF]->(sales1),
       (suzuki)-[:MEMBER_OF]->(sales2),
       (tanaka)-[:MEMBER_OF]->(dev),
       (yamada)-[:ASSIGNED {role: 'leader', since: date('2026-04-01')}]->(x),
       (sato)-[:ASSIGNED   {role: 'member', since: date('2026-04-15')}]->(x),
       (suzuki)-[:ASSIGNED {role: 'leader', since: date('2026-05-01')}]->(y);

// Q1: 営業本部（配下の部署を含む）に所属する社員  → 山田、佐藤、鈴木
MATCH (e:Employee)-[:MEMBER_OF]->(:Department)-[:SUB_OF*0..]->(:Department {name: '営業本部'})
RETURN 'Q1' AS q, e.name AS name ORDER BY name;

// Q2: リーダーが承認できる社員  → 山田 → 佐藤
MATCH (l:Employee)-[:ASSIGNED {role: 'leader'}]->(p:Project)<-[:ASSIGNED]-(m:Employee)
WHERE l <> m
RETURN 'Q2' AS q, l.name AS leader, m.name AS member;

// Q3: どのプロジェクトにも割り当てられていない社員  → 田中
MATCH (e:Employee)
WHERE NOT EXISTS { (e)-[:ASSIGNED]->(:Project) }
RETURN 'Q3' AS q, e.name AS name;
