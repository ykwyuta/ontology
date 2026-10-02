"""条文の文言から、同じ法令の中の参照（相互参照）を抽出する。

扱うもの:
  第九十五条 / 第九十八条の二 / 前条 / 次条 / 同条 / 前二条
  第三項 / 前項 / 次項 / 同項 / 前各項 / 前三項
  第一号 / 前号 / 次号 / 同号 / 前各号
  これらの連結（第九十六条第二項）、列挙での継承（第九十六条第二項及び第三項 → 3項も96条）、
  範囲（第百条から第百三条まで）
附則の中では「新法第N条」「旧法第N条」「民法第N条」を本則への参照、「附則第N条」と前条・同条などを
同じ附則の中の参照とし、前置きのない「第N条」は改正法の本則（この法令の外）への参照として除く。
他の法令への参照（「民事執行法第百六十七条」「同法第N条」など）と、かぎ括弧の中（読替え後の文言など）は除く。

参照の種類（reference-kind）は直後の文言から判定する:
  …の規定にかかわらず → notwithstanding / …を除く・除き → exclude / …中「…」とあるのは → read-as
  準用する文で「…の規定は（を）」→ apply-mutatis-mutandis / それ以外 → refer
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .kanji import KANJI_NUM_CHARS, kanji_num_path, kanji_to_int
from .lawxml import Provision, Snapshot

N = f"[{KANJI_NUM_CHARS}]+"
BR = f"(?:の{N})*"
ART = f"第{N}条{BR}|前{N}条|前条|次条|同条"
PARA = f"第{N}項|前{N}項|前各項|前項|次項|同項"
ITEM = f"第{N}号{BR}|前{N}号|前各号|前号|次号|同号"
REF_RE = re.compile(
    rf"(?P<prefix>新法|旧法|附則|同法|この法律|{{law_title}})?"
    rf"(?P<art>{ART})?(?P<para>{PARA})?(?P<item>{ITEM})?"
)
# 編・章・節・款・目への参照: この章 / 前節 / 次款 / 同節 / 前三節 / 第四款 / 前章第一節第二款
GROUP_KINDS = {"編": "part", "章": "chapter", "節": "section", "款": "subsection", "目": "division"}
GROUP_ORDER = ["part", "chapter", "section", "subsection", "division"]
_G = "[編章節款目]"
GROUP_RE = re.compile(rf"(?:この|前{N}|前|次|同|第{N})({_G})(?:第{N}{_G})*(?![的録標下次])")
GROUP_TOKEN_RE = re.compile(rf"(この|前{N}|前|次|同|第{N})({_G})")
SEP_RE = re.compile(r"^(?:、|及び|並びに|又は|若しくは|或いは)+$")
# 前の参照の条・項を引き継ぐつなぎ: 列挙、範囲（第二項から第四項まで）、括弧書き（前条（第二号に係る部分に限る。））
PAREN_RE = re.compile(r"^(?:（[^（）]*(?:（[^（）]*）[^（）]*)*）)+")  # 先頭の括弧書き（1 段の入れ子まで）
CHAIN_RE = re.compile(r"^(?:、|及び|並びに|又は|若しくは|或いは|から|（)+$")
LAW_NUM_TAIL = ("法律", "政令", "省令", "府令", "規則", "条例", "勅令", "布告", "命令")


@dataclass(frozen=True)
class Reference:
    citing: str
    cited: str
    kind: str
    text: str


@dataclass
class _Match:
    start: int
    end: int
    text: str
    targets: list[str]          # 解決した規定のパス
    article: str | None         # 継承用: 参照先の条
    para: str | None            # 継承用: 参照先の項
    main_scope: bool            # 継承用: 本則を指していたか（附則の中の「新法第N条、第M条」）
    external: bool = False      # 他の法令（改正法の本則を含む）への参照


def mask_quotes(text: str) -> str:
    """かぎ括弧の中を伏せる（入れ子に対応）。位置は保つ。"""
    out, depth = [], 0
    for c in text:
        if c == "「":
            depth += 1
            out.append(c)
        elif c == "」" and depth:
            depth -= 1
            out.append(c)
        else:
            out.append("＿" if depth else c)
    return "".join(out)


class Resolver:
    def __init__(self, snap: Snapshot):
        self.snap = snap
        self.ref_re = re.compile(REF_RE.pattern.replace("{law_title}", re.escape(snap.law_title)))

    # --- 木の操作 ---
    def ancestor(self, path: str | None, kind: str) -> str | None:
        while path is not None:
            p = self.snap.provisions[path]
            if p.kind == kind:
                return path
            path = p.parent
        return None

    def siblings(self, path: str) -> list[str]:
        p = self.snap.provisions[path]
        if p.kind == "article":
            return self.snap.articles_by_scope[p.scope]
        return self.snap.provisions[p.parent].children

    def offset(self, path: str | None, delta: int) -> str | None:
        if path is None:
            return None
        sib = self.siblings(path)
        i = sib.index(path) + delta
        return sib[i] if 0 <= i < len(sib) else None

    def preceding(self, path: str | None, count: int | None) -> list[str]:
        """前N条・前各項など。count が None なら前のすべて。"""
        if path is None:
            return []
        sib = self.siblings(path)
        i = sib.index(path)
        return sib[: i] if count is None else sib[max(0, i - count): i]

    def exists(self, path: str | None) -> str | None:
        return path if path is not None and path in self.snap.provisions else None

    # --- 抽出 ---
    def extract(self, prov: Provision) -> list[Reference]:
        cur_art = self.ancestor(prov.path, "article")
        cur_para = self.ancestor(prov.path, "paragraph")
        cur_item = prov.path if prov.kind == "item" else None
        in_suppl = prov.scope != self.snap.law_id
        last = {"article": None, "para": None, "item": None}
        out: list[Reference] = []

        for sentence in prov.sentences:
            text = mask_quotes(sentence.text)
            matches: list[_Match] = []
            for m in self.ref_re.finditer(text):
                if not (m.group("art") or m.group("para") or m.group("item")):
                    continue
                prev = matches[-1] if matches else None
                chained = prev is not None and CHAIN_RE.match(text[prev.end:m.start()] or "x") is not None
                r = self._resolve(m, text, prov, cur_art, cur_para, cur_item, in_suppl, last,
                                  prev if chained else None)
                if r is None:
                    continue
                matches.append(r)
                if r.external:
                    # 他の法令の後の「同条」「同項」を、この法令の規定に解決しない
                    last = {"article": None, "para": None, "item": None}
                elif r.targets:
                    t = r.targets[-1]
                    last["article"] = self.ancestor(t, "article") or last["article"]
                    # 条だけの参照は「同項」「同号」の指す先を変えない（「前項…第一条…同項第一号」）
                    last["para"] = self.ancestor(t, "paragraph") or last["para"]
                    if self.snap.provisions[t].kind == "item":
                        last["item"] = t

            if not in_suppl:
                matches.extend(self._grouping_refs(text, prov))
                matches.sort(key=lambda mm: mm.start)
            groups = self._group(text, matches)
            for g in groups:
                kind = self._kind(text, sentence.text, g[-1].end)
                for mm in g:
                    for t in mm.targets:
                        if t != prov.path:
                            out.append(Reference(prov.path, t, kind, mm.text))
        # 同じ文で同じ参照先が複数回出たら 1 つにまとめる
        seen, uniq = set(), []
        for r in out:
            if (r.cited, r.kind) not in seen:
                seen.add((r.cited, r.kind))
                uniq.append(r)
        return uniq

    def _grouping_siblings(self, path: str) -> list[str]:
        p = self.snap.provisions[path]
        if p.parent is not None:
            sib = self.snap.provisions[p.parent].children
        else:
            sib = [q.path for q in self.snap.provisions.values() if q.parent is None and q.scope == p.scope]
        return [x for x in sib if self.snap.provisions[x].grouping_kind == p.grouping_kind]

    def _grouping_refs(self, text: str, prov: Provision) -> list[_Match]:
        out = []
        for m in GROUP_RE.finditer(text):
            if self._external(text, m.start(), None):
                continue
            targets: list[str] = []
            for i, t in enumerate(GROUP_TOKEN_RE.finditer(m.group(0))):
                rel, kind = t.group(1), GROUP_KINDS[t.group(2)]
                if i == 0:
                    here = self._ancestor_group(prov.path, kind)
                    if rel == "この" or rel == "同":
                        targets = [here] if here else []
                    elif rel == "前" or rel == "次":
                        if here:
                            sib = self._grouping_siblings(here)
                            j = sib.index(here) + (-1 if rel == "前" else 1)
                            targets = [sib[j]] if 0 <= j < len(sib) else []
                    elif rel.startswith("前"):
                        if here:
                            sib = self._grouping_siblings(here)
                            j = sib.index(here)
                            targets = sib[max(0, j - kanji_to_int(rel[1:])): j]
                    else:  # 第N章: 一つ上の階層の中で数える
                        parent = self._parent_group_for(prov.path, kind)
                        targets = [x for x in [self._child_group(parent, kind, kanji_to_int(rel[1:]), prov)] if x]
                else:  # 前章第一節: 直前の区分の子
                    if len(targets) != 1:
                        targets = []
                        break
                    targets = [x for x in [self._child_group(targets[0], kind, kanji_to_int(rel[1:]), prov)] if x]
                if not targets:
                    break
            if targets:
                out.append(_Match(m.start(), m.end(), m.group(0), targets, None, None, True))
        return out

    def _ancestor_group(self, path: str | None, kind: str) -> str | None:
        while path is not None:
            p = self.snap.provisions[path]
            if p.kind == "grouping" and p.grouping_kind == kind:
                return path
            path = p.parent
        return None

    def _parent_group_for(self, path: str, kind: str) -> str | None:
        """「第N款」を数える範囲（款なら所属する節、なければ章…）。見つからなければ None（法令の直下）。"""
        for k in reversed(GROUP_ORDER[:GROUP_ORDER.index(kind)]):
            g = self._ancestor_group(path, k)
            if g:
                return g
        return None

    def _child_group(self, parent: str | None, kind: str, num: int, prov: Provision) -> str | None:
        if parent is None:
            children = [q.path for q in self.snap.provisions.values() if q.parent is None and q.scope == prov.scope]
        else:
            children = self.snap.provisions[parent].children
        for c in children:
            q = self.snap.provisions[c]
            if q.grouping_kind == kind and q.num == str(num):
                return c
        return None

    def _external(self, text: str, start: int, prefix: str | None) -> bool:
        if prefix == "同法":
            return True
        if prefix:
            return False
        before = text[:start]
        if before.endswith("）"):
            # 「商法（明治三十二年法律第四十八号）第五百二十六条」
            open_ = before.rfind("（")
            if open_ >= 0 and "号" in before[open_:]:
                return any(before[:open_].endswith(t) or before[:open_].endswith("法") for t in LAW_NUM_TAIL)
            return False
        return before.endswith(("法", "令", "則")) or before.endswith(LAW_NUM_TAIL)

    def _resolve(self, m, text, prov, cur_art, cur_para, cur_item, in_suppl, last, prev) -> _Match | None:
        prefix, art, para, item = m.group("prefix"), m.group("art"), m.group("para"), m.group("item")
        # 法令番号（「法律第八十九号」の「第八十九号」）は参照ではない
        if item and not art and not para and text[:m.start()].endswith(LAW_NUM_TAIL):
            return None
        if self._external(text, m.start(), prefix) or (prev is not None and prev.external and not prefix):
            return _Match(m.start(), m.end(), m.group(0), [], None, None, False, external=True)

        law = self.snap.law_id
        if prefix in ("新法", "旧法", self.snap.law_title) or (prefix == "この法律" and not in_suppl):
            scope, main_scope = law, True
        elif prefix == "附則":
            scope, main_scope = (prov.scope if in_suppl else f"{law}/sp:original"), False
        elif prev is not None and prev.main_scope:
            scope, main_scope = law, True
        else:
            scope, main_scope = prov.scope, not in_suppl

        targets_art: list[str] = []
        if art:
            if art.startswith("第"):
                if in_suppl and scope == prov.scope and prefix != "附則" and not (prev and prev.article):
                    # 附則の中の前置きのない「第N条」は改正法の本則を指す
                    return _Match(m.start(), m.end(), m.group(0), [], None, None, False, external=True)
                num = kanji_num_path(art[1:art.index("条")] + art[art.index("条") + 1:])
                targets_art = [p for p in [self.exists(f"{scope}/a{num}")] if p]
            elif art == "前条":
                targets_art = [p for p in [self.offset(cur_art, -1)] if p]
            elif art == "次条":
                targets_art = [p for p in [self.offset(cur_art, 1)] if p]
            elif art == "同条":
                targets_art = [p for p in [last["article"]] if p]
            else:  # 前N条
                targets_art = self.preceding(cur_art, kanji_to_int(art[1:-1]))
            if not targets_art:
                return _Match(m.start(), m.end(), m.group(0), [], None, None, main_scope)

        base_art = targets_art[-1] if targets_art else (prev.article if prev and prev.article else cur_art)
        targets_para: list[str] = []
        if para:
            if len(targets_art) > 1:
                return _Match(m.start(), m.end(), m.group(0), [], None, None, main_scope)
            if para.startswith("第"):
                targets_para = [p for p in [self.exists(f"{base_art}/p{kanji_to_int(para[1:-1])}")] if p]
            elif para == "前項":
                targets_para = [p for p in [self.offset(cur_para, -1)] if p]
            elif para == "次項":
                targets_para = [p for p in [self.offset(cur_para, 1)] if p]
            elif para == "同項":
                targets_para = [p for p in [last["para"]] if p]
            elif para == "前各項":
                targets_para = self.preceding(cur_para, None)
            else:  # 前N項
                targets_para = self.preceding(cur_para, kanji_to_int(para[1:-1]))
            if not targets_para:
                return _Match(m.start(), m.end(), m.group(0), [], None, None, main_scope)

        targets_item: list[str] = []
        if item:
            if len(targets_art) > 1 or len(targets_para) > 1:
                return _Match(m.start(), m.end(), m.group(0), [], None, None, main_scope)
            if targets_para:
                base_para = targets_para[0]
            elif targets_art:
                base_para = self.exists(f"{targets_art[0]}/p1")
            elif prev and prev.para:
                base_para = prev.para
            elif prev and prev.article:
                base_para = self.exists(f"{prev.article}/p1")
            else:
                base_para = cur_para
            if item.startswith("第"):
                num = kanji_num_path(item[1:item.index("号")] + item[item.index("号") + 1:])
                targets_item = [p for p in [self.exists(f"{base_para}/i{num}")] if p]
            elif item == "前号":
                targets_item = [p for p in [self.offset(cur_item, -1)] if p]
            elif item == "次号":
                targets_item = [p for p in [self.offset(cur_item, 1)] if p]
            elif item == "同号":
                targets_item = [p for p in [last["item"]] if p]
            elif item == "前各号":
                targets_item = self.preceding(cur_item, None)
            else:  # 前N号
                targets_item = self.preceding(cur_item, kanji_to_int(item[1:-1]))
            if not targets_item:
                return _Match(m.start(), m.end(), m.group(0), [], None, None, main_scope)

        targets = targets_item or targets_para or targets_art
        art_ctx = targets_art[-1] if targets_art else (self.ancestor(targets[-1], "article") if targets else None)
        para_ctx = targets_para[-1] if targets_para else (
            self.ancestor(targets[-1], "paragraph") if targets_item else None)
        return _Match(m.start(), m.end(), m.group(0), targets, art_ctx, para_ctx, main_scope)

    def _group(self, text: str, matches: list[_Match]) -> list[list[_Match]]:
        """列挙・範囲でつながった参照をまとめ、範囲（AからBまで）を展開する。"""
        groups: list[list[_Match]] = []
        for mm in matches:
            if groups:
                gap = text[groups[-1][-1].end:mm.start]
                if gap == "から" and text[mm.end:mm.end + 2] == "まで":
                    a, b = groups[-1][-1], mm
                    if len(a.targets) == 1 and len(b.targets) == 1:
                        mm.targets = self._range(a.targets[0], b.targets[0]) or b.targets
                    mm.text = f"{a.text}から{mm.text}まで"
                    mm.end += 2
                    groups[-1].append(mm)
                    continue
                if SEP_RE.match(gap or "x"):
                    groups[-1].append(mm)
                    continue
            groups.append([mm])
        return groups

    def _range(self, a: str, b: str) -> list[str]:
        sib = self.siblings(a)
        if b not in sib:
            return []
        i, j = sib.index(a), sib.index(b)
        return sib[i + 1: j + 1] if i < j else []

    @staticmethod
    def _kind(masked: str, original: str, end: int) -> str:
        after = masked[end:end + 80]
        part = r"(?:本文|ただし書|前段|後段|各号列記以外の部分|柱書)?"
        if re.match(rf"^{part}(?:の規定)?(?:に|の)?かかわらず", after):
            return "notwithstanding"
        if re.match(rf"^{part}(?:の規定)?(?:に規定する[^、。]{{0,20}}?)?を除(?:く|き)", after):
            return "exclude"
        if re.match(rf"^{part}(?:の規定)?中「", after):
            return "read-as"
        # 「第N条から第M条まで（第K条ただし書を除く。）の規定は、…について準用する」
        stripped = PAREN_RE.sub("", after)
        if re.match(rf"^{part}(?:の規定)?(?:に|の)?かかわらず", stripped):
            return "notwithstanding"
        if ("準用" in masked[end:] and not stripped.startswith("において準用")
                and re.match(rf"^{part}(?:及び[^、。]{{0,10}})?の規定", stripped)):
            return "apply-mutatis-mutandis"
        return "refer"


def extract_all(snap: Snapshot) -> list[Reference]:
    r = Resolver(snap)
    out: list[Reference] = []
    for p in snap.provisions.values():
        if p.sentences:
            out.extend(r.extract(p))
    return out
