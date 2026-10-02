# 規範（規範層の正本）

ここにある YAML が規範層の正本です。`legal-onto load-norms` で検証してから TypeDB に書き込み、TypeQL の関数にコンパイルします。

**レビュー状態**: すべて `unreviewed`（法律の専門家による確認なし）。根拠条文の文言は、取り込み時に条文層と自動で照合しています（`quote`）。要件の立て方と証明責任の配分は、下記の典拠に基づいて作成者が書いたもので、典拠の頁との照合はまだしていません。[docs/proposal/06-decisions.md](../docs/proposal/06-decisions.md) の方針どおり、出力のたびにこの状態を表示します。

## 書式

```yaml
- id: D95                       # 規範ID（英数字と - _）
  label: 錯誤取消し
  effect: cancellation-by-mistake
  category: impeding            # arising 発生 / impeding 障害 / extinguishing 消滅 / blocking 阻止 / auxiliary 部品
  claim-type: sale-price        # arising（請求原因）のとき: 対象の訴訟物
  exception-of: [G555-price]    # この規範が例外として働く規範（抗弁なら請求原因、再抗弁なら抗弁）
  valid-from: 2020-04-01        # 適用期間（省略可）
  time-anchor: declaration      # 適用期間を判定する時点の種類（valid-from / valid-to があるときは必須）
  stance: 条文                  # 条文 / 判例 / 通説 / 有力説:○○
  sources:                      # 根拠条文（provision-path の法令ID 以降）と、その文言の一部
    - path: a95/p1
      quote: 取り消すことができる
  precedents: []                # 判例（引用表記）
  authority:                    # 典拠（要件の立て方・証明責任の配分）
    - 司法研修所編『紛争類型別の要件事実』（売買代金請求訴訟）
  note: 補足
  when:                         # 要件の木
    all:
      - norm: NR95              # 他の規範の成立
      - fact: N123.cancellation-declared
        label: 取消しの意思表示をしたこと
        evaluative: false       # 規範的要件なら true（評価は利用者が入力する）
```

要件の木は `all`（かつ）・`any`（または）・`fact`・`norm` を入れ子にできます。

## 時点の種類（time-anchor）

平成29年法律第44号（債権法改正）の附則に従い、改正後の規定を適用するかどうかを決める時点です。事案の入力で日付を与えます。

| 値 | 時点 | 附則 |
|----|------|------|
| `declaration` | 意思表示をした時 | 6条1項 |
| `contract` | 契約を締結した時 | 34条1項 |
| `claim-arose` | 債権が生じた時（その原因である法律行為の時を含む） | 10条1項・4項 |

改正前の規定（旧法）の規範はまだ登録していません（フェーズ3）。時点が施行日（2020-04-01）より前の事案では、該当する規範が適用されず、評価結果にその旨の警告が出ます。

## 証明責任

各規範の層（請求原因 0、抗弁 1、再抗弁 2、再々抗弁 3 …）は `exception-of` の関係から計算し、要件事実の証明責任を、層が偶数なら請求する側（claimant）、奇数なら請求される側（respondent）に割り当てます。
