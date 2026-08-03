#!/usr/bin/env python3
"""Convert national statute XML (Canada, New Zealand) to Akoma Ntoso 3.0.

Two jurisdictions in the corpus never went through an AKN conversion: they ship
in the native XML their legislature publishes, which carries no eId attributes at
all, so scripts/article_locator.py cannot resolve a reference like "s. 6
Copyright Act" and the document panel stays empty.

    Canada       Justice Laws "Statute" XML   (<Statute>/<Body>/<Section>)
    New Zealand  PCO legislation XML          (<act>/<body>/<prov>)

scripts/01_convert_html_to_akn.py cannot be reused: it parses the cleaned WIPO
treaty HTML with BeautifulSoup and is driven by TREATY_SPECS, so it has no notion
of either schema. Hence this separate converter, with one adapter per format.

Both adapters emit the same AKN subset the rest of the pipeline consumes:

    <akomaNtoso><act><meta><identification> … FRBR block … </identification>
      <body>
        <part eId="part_1">|<hcontainer name="crossHeading" eId="crossheading_2">
          <section eId="sec_6"><num>6</num><heading>…</heading>
            <subsection eId="sec_6__subsec_1"><num>(1)</num>
              <content><p>…</p><blockList>…</blockList></content>

eIds follow the convention already used by the German and French documents
(``sec_64``, ``art_1__para_1``), which is what article_locator.py expects.

Schedules are deliberately skipped. New Zealand repeats section numbers inside
Schedule 1 (there is a second "22" and a second "16"), and the locator returns
the first match it walks into, so including them would make references
ambiguous. The Canadian schedules are treaty reprints, not operative sections.

Run:
    uv run python scripts/04_convert_national_xml_to_akn.py            # both
    uv run python scripts/04_convert_national_xml_to_akn.py --only nz
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NSMAP = {None: AKN_NS}

# --- Canada ----------------------------------------------------------------
CA_SRC = Path("data/countries/ca/copyright/C-42.xml")
CA_DST = Path("data/countries/ca/copyright/akn/C-42_akn.xml")
CA_SOURCE_URL = "https://laws-lois.justice.gc.ca/eng/acts/C-42/"
# Text-bearing children of a Canadian provision; everything else is editorial
CA_TEXT_TAGS = {"Text", "ContinuedSectionSubsection", "ContinuedParagraph"}

# --- New Zealand -----------------------------------------------------------
NZ_SRC = Path("data/countries/nz/copyright/096be8ed81fe312e.xml")
NZ_DST = Path("data/countries/nz/copyright/akn/copyright_act_1994_akn.xml")
NZ_SOURCE_URL = (
    "https://www.legislation.govt.nz/act/public/1994/0143/latest/DLM345633.html"
)
# Amendment history and cross-reference notes carry no normative text
NZ_SKIP_TAGS = {
    "history-note", "history", "cf", "amendment-date", "amending-operation",
    "amended-provision", "amending-leg", "editorial-note", "note",
}


# ---------------------------------------------------------------------------
# Small XML helpers
# ---------------------------------------------------------------------------

def _el(parent, tag: str, **attrs) -> etree._Element:
    child = etree.SubElement(parent, f"{{{AKN_NS}}}{tag}", nsmap=None)
    for key, value in attrs.items():
        if value:
            child.set(key, value)
    return child


def _text_el(parent, tag: str, text: str, **attrs) -> etree._Element:
    child = _el(parent, tag, **attrs)
    child.text = text
    return child


def _norm(text: str | None) -> str:
    """Collapse whitespace; the source files are pretty-printed."""
    return re.sub(r"\s+", " ", text or "").strip()


def _inline_text(el: etree._Element | None, skip: set[str] = frozenset()) -> str:
    """Plain text of *el*, skipping *skip* subtrees and nested block children."""
    if el is None:
        return ""
    chunks: list[str] = []

    def walk(node: etree._Element, top: bool) -> None:
        if not top and etree.QName(node.tag).localname in skip:
            return
        if node.text:
            chunks.append(node.text)
        for kid in node:
            walk(kid, False)
            if kid.tail:
                chunks.append(kid.tail)

    walk(el, True)
    return _norm("".join(chunks))


def _slug(label: str) -> str:
    """'2.1' → '2_1', '(1)' → '1', 'PART I' → 'i'."""
    cleaned = re.sub(r"^(part|schedule)\s+", "", label.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", cleaned).strip("_")
    return cleaned.lower()


# ---------------------------------------------------------------------------
# Shared AKN scaffolding
# ---------------------------------------------------------------------------

def _new_document(
    *,
    act_name: str,
    work_uri: str,
    expression_uri: str,
    country: str,
    enacted: str,
    applicability: str,
    language: str,
    source_url: str,
    title: str,
) -> tuple[etree._Element, etree._Element]:
    """Return (root, body) of a fresh AKN act with a populated FRBR block."""
    root = etree.Element(f"{{{AKN_NS}}}akomaNtoso", nsmap=_NSMAP)
    act  = _el(root, "act", name=act_name)
    meta = _el(act, "meta")
    ident = _el(meta, "identification", source="#converter")

    work = _el(ident, "FRBRWork")
    _el(work, "FRBRthis", value=f"{work_uri}/!main")
    _el(work, "FRBRuri", value=work_uri)
    if enacted:
        _el(work, "FRBRdate", date=enacted, name="enacted")
    _el(work, "FRBRauthor", href="#legislature")
    _el(work, "FRBRcountry", value=country)
    _el(work, "FRBRname", value=title)
    _el(work, "FRBRalias", name="sourceUri", value=source_url)
    # The corpus copy is a conversion of the official XML, not the official
    # expression itself, so it must not claim authenticity.
    _el(work, "FRBRauthoritative", value="false")

    expr = _el(ident, "FRBRExpression")
    _el(expr, "FRBRthis", value=f"{expression_uri}/!main")
    _el(expr, "FRBRuri", value=expression_uri)
    if applicability:
        _el(expr, "FRBRdate", date=applicability, name="dateApplicability")
    _el(expr, "FRBRauthor", href="#legislature")
    _el(expr, "FRBRlanguage", language=language)

    manif = _el(ident, "FRBRManifestation")
    _el(manif, "FRBRthis", value=f"{expression_uri}/!main.xml")
    _el(manif, "FRBRuri", value=f"{expression_uri}.akn")
    _el(manif, "FRBRformat", value="application/akn+xml")

    preface = _el(act, "preface")
    _text_el(preface, "p", title)

    body = _el(act, "body")
    return root, body


def _write(root: etree._Element, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tree = etree.ElementTree(root)
    tree.write(str(dst), pretty_print=True, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------------------
# Content builder shared by both adapters
# ---------------------------------------------------------------------------

def _add_content(parent, blocks: list[tuple[str, str, list[tuple[str, str]]]]) -> None:
    """Fill a <content> element.

    *blocks* is a list of (kind, text, items) where kind is "p" for a plain
    paragraph or "list" for a lettered/numbered list whose *text* is the
    introduction and *items* are (label, text) pairs.
    """
    if not blocks:
        return
    content = _el(parent, "content")
    for kind, text, items in blocks:
        if kind == "p":
            if text:
                _text_el(content, "p", text)
            continue
        block = _el(content, "blockList")
        if text:
            _text_el(block, "listIntroduction", text)
        for label, item_text in items:
            item = _el(block, "item")
            if label:
                _text_el(item, "num", label)
            _text_el(item, "p", item_text)


# ---------------------------------------------------------------------------
# Canada: Justice Laws LIMS "Statute" XML
# ---------------------------------------------------------------------------

def _ca_blocks(container: etree._Element) -> list[tuple[str, str, list]]:
    """Turn Text/Paragraph children of a Section or Subsection into blocks."""
    blocks: list[tuple[str, str, list]] = []
    children = [c for c in container if isinstance(c.tag, str)]
    intro = ""
    index = 0

    while index < len(children):
        child = children[index]
        tag = etree.QName(child.tag).localname

        if tag in CA_TEXT_TAGS:
            text = _inline_text(child)
            nxt = children[index + 1] if index + 1 < len(children) else None
            if nxt is not None and etree.QName(nxt.tag).localname == "Paragraph":
                intro = text          # introduces the list that follows
            elif text:
                blocks.append(("p", text, []))
            index += 1
            continue

        if tag == "Paragraph":
            items: list[tuple[str, str]] = []
            while index < len(children) and etree.QName(children[index].tag).localname == "Paragraph":
                items.extend(_ca_items(children[index]))
                index += 1
            blocks.append(("list", intro, items))
            intro = ""
            continue

        index += 1

    return blocks


def _ca_items(para: etree._Element, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten a Paragraph (and its Subparagraphs) into (label, text) pairs."""
    label = _norm(_inline_text(para.find("Label")))
    label = f"{prefix}{label}"
    text  = " ".join(
        t for t in (_inline_text(c) for c in para if etree.QName(c.tag).localname in CA_TEXT_TAGS) if t
    )
    items = [(label, text)]
    for sub in para:
        if etree.QName(sub.tag).localname in ("Subparagraph", "Clause"):
            items.extend(_ca_items(sub, prefix=label))
    return items


def _ca_subsection(parent, subsec: etree._Element, section_eid: str, ordinal: int) -> None:
    label = _norm(_inline_text(subsec.find("Label")))
    eid   = f"{section_eid}__subsec_{_slug(label) or ordinal}"
    el    = _el(parent, "subsection", eId=eid)
    if label:
        _text_el(el, "num", label)
    marginal = subsec.find("MarginalNote")
    if marginal is not None:
        _text_el(el, "heading", _inline_text(marginal))
    _add_content(el, _ca_blocks(subsec))


def _ca_section(parent, section: etree._Element) -> None:
    label = _norm(_inline_text(section.find("Label")))
    if not label:
        return
    eid = f"sec_{_slug(label)}"
    el  = _el(parent, "section", eId=eid)
    _text_el(el, "num", label)

    marginal = section.find("MarginalNote")
    if marginal is not None:
        _text_el(el, "heading", _inline_text(marginal))

    subsections = section.findall("Subsection")
    if subsections:
        # Text sitting directly on the section introduces the subsections
        lead = [c for c in section if etree.QName(c.tag).localname in CA_TEXT_TAGS]
        if lead:
            intro = _el(el, "subsection", eId=f"{eid}__intro")
            _add_content(intro, [("p", _inline_text(c), []) for c in lead])
        for ordinal, subsec in enumerate(subsections, start=1):
            _ca_subsection(el, subsec, eid, ordinal)
    else:
        _add_content(el, _ca_blocks(section))


def convert_canada(src: Path = CA_SRC, dst: Path = CA_DST) -> Path:
    root_src = etree.parse(str(src)).getroot()
    lims = "{http://justice.gc.ca/lims}"
    ident = root_src.find("Identification")

    def ident_text(tag: str) -> str:
        el = ident.find(tag) if ident is not None else None
        return _inline_text(el)

    short_title = ident_text("ShortTitle") or "Copyright Act"
    number      = ident_text("ConsolidatedNumber") or "C-42"
    applicable  = root_src.get(f"{lims}pit-date", "")
    work_uri    = f"/akn/ca/act/1985/{number.lower()}"
    expr_uri    = f"{work_uri}/eng@{applicable}" if applicable else f"{work_uri}/eng"

    root, body = _new_document(
        act_name="statute",
        work_uri=work_uri,
        expression_uri=expr_uri,
        country="CA",
        enacted="1985-12-31",       # R.S.C., 1985 consolidation
        applicability=applicable,
        language="eng",
        source_url=CA_SOURCE_URL,
        title=f"{short_title} (R.S.C., 1985, c. {number})",
    )

    src_body = root_src.find("Body")
    if src_body is None:
        raise SystemExit(f"{src}: no <Body> element")

    # Headings are flat siblings carrying a level attribute; rebuild the nesting
    stack: list[tuple[int, etree._Element]] = [(0, body)]
    counters = {"part": 0, "cross": 0}

    for child in src_body:
        tag = etree.QName(child.tag).localname

        if tag == "Heading":
            level = int(child.get("level", "1") or 1)
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1]
            label  = _inline_text(child.find("Label"))
            title  = _inline_text(child.find("TitleText"))
            if label.upper().startswith("PART"):
                counters["part"] += 1
                container = _el(parent, "part", eId=f"part_{_slug(label) or counters['part']}")
                _text_el(container, "num", label)
            else:
                counters["cross"] += 1
                container = _el(
                    parent, "hcontainer",
                    name="crossHeading", eId=f"crossheading_{counters['cross']}",
                )
            if title:
                _text_el(container, "heading", title)
            stack.append((level, container))
            continue

        if tag == "Section":
            _ca_section(stack[-1][1], child)

    _write(root, dst)
    return dst


# ---------------------------------------------------------------------------
# New Zealand: PCO legislation XML
# ---------------------------------------------------------------------------

def _nz_items(label_para: etree._Element, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten a <label-para> (and nested ones) into (label, text) pairs."""
    label = _norm(_inline_text(label_para.find("label")))
    label = f"{prefix}({label})" if label else prefix
    para  = label_para.find("para")
    text  = ""
    nested: list[tuple[str, str]] = []
    if para is not None:
        text = " ".join(
            t for t in (_inline_text(c, NZ_SKIP_TAGS) for c in para
                        if etree.QName(c.tag).localname == "text") if t
        )
        for kid in para:
            if etree.QName(kid.tag).localname == "label-para":
                nested.extend(_nz_items(kid, prefix=label))
    return [(label, text)] + nested


def _nz_blocks(para: etree._Element) -> list[tuple[str, str, list]]:
    """Turn a <para> into content blocks, lifting <label-para> into a list.

    A <text> immediately followed by <label-para> siblings is the list
    introduction rather than a paragraph of its own.
    """
    sequence: list[tuple[str, str, list]] = []
    for child in para:
        tag = etree.QName(child.tag).localname
        if tag in NZ_SKIP_TAGS:
            continue
        if tag == "text":
            text = _inline_text(child, NZ_SKIP_TAGS)
            if text:
                sequence.append(("text", text, []))
        elif tag == "label-para":
            sequence.append(("item", "", _nz_items(child)))

    blocks: list[tuple[str, str, list]] = []
    index = 0
    while index < len(sequence):
        kind, text, items = sequence[index]

        if kind == "text":
            if index + 1 < len(sequence) and sequence[index + 1][0] == "item":
                index += 1
                blocks.append(("list", text, _nz_item_run(sequence, index)))
                while index < len(sequence) and sequence[index][0] == "item":
                    index += 1
                continue
            blocks.append(("p", text, []))
            index += 1
            continue

        blocks.append(("list", "", _nz_item_run(sequence, index)))
        while index < len(sequence) and sequence[index][0] == "item":
            index += 1

    return blocks


def _nz_item_run(sequence: list[tuple[str, str, list]], start: int) -> list[tuple[str, str]]:
    """Flatten the run of consecutive item entries beginning at *start*."""
    run: list[tuple[str, str]] = []
    index = start
    while index < len(sequence) and sequence[index][0] == "item":
        run.extend(sequence[index][2])
        index += 1
    return run


def _nz_prov(parent, prov: etree._Element) -> None:
    label = _norm(_inline_text(prov.find("label")))
    if not label:
        return
    eid = f"sec_{_slug(label)}"
    el  = _el(parent, "section", eId=eid)
    _text_el(el, "num", label)

    heading = prov.find("heading")
    if heading is not None:
        _text_el(el, "heading", _inline_text(heading))

    prov_body = prov.find("prov.body")
    if prov_body is None:
        return

    subprovs = prov_body.findall("subprov")
    if not subprovs:
        blocks: list[tuple[str, str, list]] = []
        for para in prov_body.findall("para"):
            blocks.extend(_nz_blocks(para))
        _add_content(el, blocks)
        return

    for ordinal, subprov in enumerate(subprovs, start=1):
        label_el  = subprov.find("label")
        numbered  = label_el is not None and label_el.get("denominator") != "no"
        sub_label = _norm(_inline_text(label_el)) if numbered else ""
        sub_eid   = f"{eid}__subsec_{_slug(sub_label) or ordinal}"
        sub_el    = _el(el, "subsection", eId=sub_eid)
        if sub_label:
            _text_el(sub_el, "num", f"({sub_label})")
        blocks = []
        for para in subprov.findall("para"):
            blocks.extend(_nz_blocks(para))
        _add_content(sub_el, blocks)


def convert_new_zealand(src: Path = NZ_SRC, dst: Path = NZ_DST) -> Path:
    root_src   = etree.parse(str(src)).getroot()
    act_no     = root_src.get("act.no", "143")
    year       = root_src.get("year", "1994")
    assent     = root_src.get("date.assent", "")
    as_at      = root_src.get("date.as.at", "")
    title_el   = root_src.find(".//title")
    title      = _inline_text(title_el) or "Copyright Act 1994"

    work_uri = f"/akn/nz/act/{year}/{act_no}"
    expr_uri = f"{work_uri}/eng@{as_at}" if as_at else f"{work_uri}/eng"

    root, body = _new_document(
        act_name="act",
        work_uri=work_uri,
        expression_uri=expr_uri,
        country="NZ",
        enacted=assent,
        applicability=as_at,
        language="eng",
        source_url=NZ_SOURCE_URL,
        title=f"{title} (Public Act {year} No {act_no})",
    )

    src_body = root_src.find("body")
    if src_body is None:
        raise SystemExit(f"{src}: no <body> element")

    cross = 0

    def walk(src_parent: etree._Element, dst_parent: etree._Element) -> None:
        nonlocal cross
        current = dst_parent
        for child in src_parent:
            tag = etree.QName(child.tag).localname
            if tag in ("part", "subpart"):
                label = _norm(_inline_text(child.find("label")))
                kind  = "part" if tag == "part" else "chapter"
                container = _el(dst_parent, kind, eId=f"{kind}_{_slug(label) or 'x'}")
                if label:
                    _text_el(container, "num", f"{'Part' if tag == 'part' else 'Subpart'} {label}")
                heading = child.find("heading")
                if heading is not None:
                    _text_el(container, "heading", _inline_text(heading))
                current = container
                walk(child, container)
            elif tag == "crosshead":
                cross += 1
                current = _el(
                    dst_parent, "hcontainer",
                    name="crossHeading", eId=f"crossheading_{cross}",
                )
                heading = child.find("heading") if child.find("heading") is not None else child
                _text_el(current, "heading", _inline_text(heading))
            elif tag == "prov":
                _nz_prov(current, child)

    walk(src_body, body)
    _write(root, dst)
    return dst


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["ca", "nz"], help="convert a single jurisdiction")
    args = parser.parse_args()

    targets = {"ca": convert_canada, "nz": convert_new_zealand}
    if args.only:
        targets = {args.only: targets[args.only]}

    for code, convert in targets.items():
        try:
            out = convert()
        except Exception as exc:                       # noqa: BLE001
            print(f"[{code}] FAILED: {exc}", file=sys.stderr)
            continue
        root = etree.parse(str(out)).getroot()
        sections = len(root.findall(f".//{{{AKN_NS}}}section"))
        print(f"[{code}] {out}  ({sections} sections)")


if __name__ == "__main__":
    main()
