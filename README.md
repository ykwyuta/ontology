# ontology-legal

TypeDB で日本法（まず民法の意思表示・売買・消滅時効）を表現し、法的判断をクエリで引き出すための実務家向け支援ツール。

- 教科書（エンジニアのためのオントロジー入門）: [docs/userguide/README.md](docs/userguide/README.md)
- 提案と設計: [docs/proposal/README.md](docs/proposal/README.md)
- 決定事項: [docs/proposal/06-decisions.md](docs/proposal/06-decisions.md)
- フェーズ1（条文層）の結果: [docs/proposal/07-phase1-results.md](docs/proposal/07-phase1-results.md)
- フェーズ2（規範層とコンパイラ）の結果: [docs/proposal/08-phase2-results.md](docs/proposal/08-phase2-results.md)
- 規範（正本）: [norms/](norms/)

## 開発環境

前提: Docker（compose v2）、Python 3.12 以上

```bash
docker compose up -d
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/legal-onto init-db
.venv/Scripts/legal-onto import-law 129AC0000000089     # 民法（2016-10-13 以降の全版）
.venv/Scripts/legal-onto load-norms                      # norms/*.yaml を検証・コンパイル
.venv/Scripts/python -m pytest
```

TypeDB CE は gRPC `127.0.0.1:1729`、HTTP `127.0.0.1:8000` で待ち受ける（ユーザー `admin` / 初期パスワード `password`、TLS なし。ローカル開発専用）。
接続先は環境変数 `TYPEDB_ADDRESS` / `TYPEDB_USERNAME` / `TYPEDB_PASSWORD` / `TYPEDB_DATABASE`（既定 `legal`）で変えられる。

## 使い方の例

```bash
# 事案を評価する（提案書 4.5 の例題）
.venv/Scripts/legal-onto evaluate cases/demo-001.yaml
# 2019年6月1日時点の民法95条（改正前: 錯誤は無効）
.venv/Scripts/legal-onto text 129AC0000000089/a95 --at 2019-06-01
# 95条（項・号を含む）を参照している規定
.venv/Scripts/legal-onto refs 129AC0000000089/a95 --reverse --at 2024-05-10
# 249条を含む節への参照（「この節の規定は…準用する」）も含めた被参照
.venv/Scripts/legal-onto refs 129AC0000000089/a249 --reverse --at 2024-05-10 --with-containers
```
