"""法令標準XML の解析。1 つの版（スナップショット）を規定単位の木に変換する。

規定のパス（provision-path）の規則:
  本則の条      {law-id}/a{Num}                     例: 129AC0000000089/a98_2
  項・号        .../p{Num}/i{Num}/si1-{Num}/si2-{Num}...
  編章節款目    {law-id}/pt{Num}/ch{Num}/se{Num}/ss{Num}/dv{Num}
  附則          {law-id}/sp:{改正法令番号 または original}  その下の条・項も同じ規則
条は編章節の下にあっても条番号だけでパスを作る（本則の中で条番号は一意で、所属する章が改正で変わってもパスが変わらないようにするため）。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

GROUPINGS = {
    "Part": ("part", "pt", "PartTitle"),
    "Chapter": ("chapter", "ch", "ChapterTitle"),
    "Section": ("section", "se", "SectionTitle"),
    "Subsection": ("subsection", "ss", "SubsectionTitle"),
    "Division": ("division", "dv", "DivisionTitle"),
}
SUBITEM_LEVELS = 10


@dataclass(frozen=True)
class Sentence:
    num: int
    function: str | None   # "main", "proviso" など。XML に指定がなければ None
    text: str


@dataclass
class Provision:
    path: str
    kind: str                       # "grouping", "article", "paragraph", "item"
    num: str | None
    caption: str | None = None
    grouping_kind: str | None = None
    parent: str | None = None       # None なら法令の直下
    sentences: tuple[Sentence, ...] = ()
    children: list[str] = field(default_factory=list)
    scope: str = ""                 # 参照解決の範囲: 本則なら law-id、附則なら附則のパス

    def content_key(self) -> tuple:
        """版の同一性の判定に使う内容。"""
        return (self.caption, self.sentences)


@dataclass
class Snapshot:
    law_id: str
    law_title: str
    law_num: str
    provisions: dict[str, Provision]
    # 参照解決の範囲ごとの条のパス（出現順）
    articles_by_scope: dict[str, list[str]]

    def article(self, scope: str, num: str) -> str | None:
        path = f"{scope}/a{num}"
        return path if path in self.provisions else None


def _text(el: ET.Element) -> str:
    """ルビの読み（Rt）を除いた文字列。"""
    out = []

    def walk(e: ET.Element) -> None:
        if e.tag == "Rt":
            return
        if e.text:
            out.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                out.append(c.tail)

    walk(el)
    return "".join(out).strip()


def _sentences(container: ET.Element | None) -> tuple[Sentence, ...]:
    """ParagraphSentence / ItemSentence など。Column（号の表形式）は全角空白でつなぐ。"""
    if container is None:
        return ()
    columns = container.findall("Column")
    if columns:
        text = "　".join(" ".join(_text(s) for s in col.findall("Sentence")) for col in columns)
        return (Sentence(1, None, text),)
    return tuple(
        Sentence(int(s.get("Num", i + 1)), s.get("Function"), _text(s))
        for i, s in enumerate(container.findall("Sentence"))
    )


class _Builder:
    def __init__(self, law_id: str):
        self.law_id = law_id
        self.provisions: dict[str, Provision] = {}
        self.articles_by_scope: dict[str, list[str]] = {}

    def add(self, p: Provision) -> None:
        if p.path in self.provisions:
            raise ValueError(f"duplicate provision path: {p.path}")
        self.provisions[p.path] = p
        if p.parent is not None:
            self.provisions[p.parent].children.append(p.path)

    def grouping(self, el: ET.Element, parent: str | None, base: str, scope: str) -> None:
        kind, prefix, title_tag = GROUPINGS[el.tag]
        path = f"{base}/{prefix}{el.get('Num')}"
        title = el.find(title_tag)
        self.add(Provision(path, "grouping", el.get("Num"), _text(title) if title is not None else None,
                           grouping_kind=kind, parent=parent, scope=scope))
        self.body(el, path, path, scope)

    def body(self, el: ET.Element, parent: str | None, base: str, scope: str) -> None:
        for c in el:
            if c.tag in GROUPINGS:
                self.grouping(c, parent, base, scope)
            elif c.tag == "Article":
                self.article(c, parent, scope)
            elif c.tag == "Paragraph":
                self.paragraph(c, parent, scope, scope)

    def article(self, el: ET.Element, parent: str | None, scope: str) -> None:
        path = f"{scope}/a{el.get('Num')}"
        cap = el.find("ArticleCaption")
        self.add(Provision(path, "article", el.get("Num"), _text(cap) if cap is not None else None,
                           parent=parent, scope=scope))
        self.articles_by_scope.setdefault(scope, []).append(path)
        for p in el.findall("Paragraph"):
            self.paragraph(p, path, path, scope)

    def paragraph(self, el: ET.Element, parent: str | None, base: str, scope: str) -> None:
        path = f"{base}/p{el.get('Num')}"
        cap = el.find("ParagraphCaption")
        self.add(Provision(path, "paragraph", el.get("Num"), _text(cap) if cap is not None else None,
                           parent=parent, sentences=_sentences(el.find("ParagraphSentence")), scope=scope))
        for it in el.findall("Item"):
            self.item(it, path, "i", "ItemSentence", 1, scope)

    def item(self, el: ET.Element, parent: str, prefix: str, sentence_tag: str, level: int, scope: str) -> None:
        path = f"{parent}/{prefix}{el.get('Num')}"
        self.add(Provision(path, "item", el.get("Num"), parent=parent,
                           sentences=_sentences(el.find(sentence_tag)), scope=scope))
        if level <= SUBITEM_LEVELS:
            tag = f"Subitem{level}"
            for sub in el.findall(tag):
                self.item(sub, path, f"si{level}-", f"{tag}Sentence", level + 1, scope)


def parse(xml: str, law_id: str) -> Snapshot:
    root = ET.fromstring(xml)
    b = _Builder(law_id)
    body = root.find("LawBody")
    main = body.find("MainProvision")
    b.body(main, None, law_id, law_id)

    seen: dict[str, int] = {}
    for sp in body.findall("SupplProvision"):
        key = sp.get("AmendLawNum") or "original"
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        path = f"{law_id}/sp:{key}"
        label = sp.find("SupplProvisionLabel")
        caption = _text(label) if label is not None else "附則"
        if sp.get("AmendLawNum"):
            caption = f"{caption}（{sp.get('AmendLawNum')}）"
        b.add(Provision(path, "grouping", key, caption, grouping_kind="suppl-provision", scope=path))
        b.body(sp, path, path, path)

    return Snapshot(
        law_id=law_id,
        law_title=_text(body.find("LawTitle")),
        law_num=_text(root.find("LawNum")),
        provisions=b.provisions,
        articles_by_scope=b.articles_by_scope,
    )
