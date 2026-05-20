#!/usr/bin/env python3
"""Convert cleaned WIPO HTML treaties to Akoma Ntoso 3.0 (AKN4UN profile)."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree

from common import (
    AKN_NS,
    TREATY_SPECS,
    TreatySpec,
    build_work_iri,
    canonical_article_token,
    canonical_marker_token,
    compare_similarity,
    ensure_dir,
    extract_date_from_text,
    is_roman,
    json_dump,
    local_name,
    looks_like_date_line,
    looks_like_editorial_note,
    looks_like_toc_heading,
    make_slug,
    normalize_for_compare,
    normalize_space,
    output_file_name,
    today_iso,
)


ARTICLE_RE = re.compile(
    r"^Article\s+([0-9IVXLCDM]+(?:\s*(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?)\b\s*[:\-–]?\s*(.*)$",
    flags=re.IGNORECASE,
)

CONTAINER_RE = re.compile(
    r"^(CHAPTER|PART|TITLE|BOOK)\s+([0-9IVXLCDM]+)\b\s*[:\-–]?\s*(.*)$",
    flags=re.IGNORECASE,
)

ROMAN_SPLIT_RE = re.compile(r"^([IVXLCDM]+)\b\s+(.*)$")

PAREN_NUM_RE = re.compile(r"^\(([0-9]+)\)\s*(.*)$")
PAREN_ALPHA_RE = re.compile(r"^\(([A-Za-z]+)\)\s*(.*)$")
DOTTED_NUM_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)+(?:\s*\([A-Za-z]+\))?)\s*(.*)$")
ALPHA_DOT_RE = re.compile(r"^([A-Za-z])\.\s*(.*)$")
NUM_DOT_RE = re.compile(r"^([0-9]+)\.\s*(.*)$")
ROMAN_CLOSE_RE = re.compile(r"^([ivxlcdm]+)\)\s*(.*)$", flags=re.IGNORECASE)
BULLET_RE = re.compile(r"^-\s*(.*)$")

BLOCK_LEVEL_TAGS = {
    "article",
    "aside",
    "blockquote",
    "dd",
    "div",
    "dl",
    "dt",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}


@dataclass
class Entry:
    text: str
    depth: int
    is_bold_like: bool


@dataclass
class Block:
    raw_text: str
    text: str
    depth: int
    marker_raw: Optional[str] = None
    marker_token: Optional[str] = None


@dataclass
class ContainerHeading:
    kind: str
    num: str
    heading: str
    split_hint: bool = False

    @property
    def key(self) -> str:
        base = f"{self.kind}:{self.num}:{self.heading.lower()}"
        return make_slug(base)


@dataclass
class ArticleData:
    token: str
    display_num: str
    heading: str
    container_key: Optional[str]
    blocks: List[Block] = field(default_factory=list)


@dataclass
class SegmentData:
    title: str
    pre_article_lines: List[str] = field(default_factory=list)
    articles: List[ArticleData] = field(default_factory=list)
    container_order: List[ContainerHeading] = field(default_factory=list)


@dataclass
class OutputDoc:
    spec: TreatySpec
    source_file: str
    short_name: str
    date_iso: str
    year: int
    title: str
    xml_tree: etree._ElementTree
    text_source: str
    stats: Dict[str, int]


def ns(tag: str) -> str:
    return f"{{{AKN_NS}}}{tag}"


def inline_text(node: object) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""

    name = (node.name or "").lower()
    if name == "br":
        return " "
    if name in BLOCK_LEVEL_TAGS:
        return ""

    return " ".join(inline_text(child) for child in node.children)


def paragraph_inline_text(p: Tag) -> str:
    return normalize_space(" ".join(inline_text(child) for child in p.children))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/wipo/html_cleaned"),
        help="Directory containing cleaned WIPO HTML files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/wipo/akns"),
        help="Directory for generated AKN XML files.",
    )
    parser.add_argument(
        "--metadata-index",
        type=Path,
        default=Path("data/wipo/akns/_metadata_index.json"),
        help="Metadata index JSON written for downstream enrichment.",
    )
    return parser.parse_args()


def collect_entries(soup: BeautifulSoup) -> List[Entry]:
    entries: List[Entry] = []
    body = soup.body
    if body is None:
        return entries

    for p in body.find_all("p"):
        if p.find_parent("table") is not None:
            continue
        text = paragraph_inline_text(p)
        if not text:
            continue
        if looks_like_toc_heading(text):
            continue
        if looks_like_editorial_note(text):
            continue
        depth = sum(1 for parent in p.parents if getattr(parent, "name", "") in {"ul", "ol"})
        bold_chunks = [paragraph_inline_text(tag) for tag in p.find_all(["b", "strong"])]
        bold_chunks = [chunk for chunk in bold_chunks if chunk]
        bold_text = normalize_space(" ".join(bold_chunks))
        is_bold_like = bool(bold_text) and (len(bold_text) >= max(6, int(0.6 * len(text))))

        entries.append(Entry(text=text, depth=depth, is_bold_like=is_bold_like))

    return entries


def parse_article_heading(text: str) -> Optional[Tuple[str, str, str]]:
    match = ARTICLE_RE.match(text)
    if not match:
        return None

    raw_num = normalize_space(match.group(1)).replace(" ", "")
    canonical = canonical_article_token(raw_num)
    if canonical.isalpha():
        display_num = canonical.upper()
    else:
        display_num = canonical

    heading = normalize_space(match.group(2)).lstrip(":- ")
    return canonical, display_num, heading


def parse_container_heading(text: str) -> Optional[ContainerHeading]:
    match = CONTAINER_RE.match(text)
    if match:
        kind = match.group(1).lower()
        num = normalize_space(match.group(2)).upper()
        heading = normalize_space(match.group(3))
        return ContainerHeading(kind=kind, num=num, heading=heading, split_hint=False)

    match = ROMAN_SPLIT_RE.match(text)
    if not match:
        return None

    num = normalize_space(match.group(1)).upper()
    heading = normalize_space(match.group(2))
    if re.search(r"\b(act|additional act|protocol|agreement)\b", heading, flags=re.IGNORECASE):
        return ContainerHeading(kind="part", num=num, heading=heading, split_hint=True)

    return None


def extract_marker(text: str) -> Tuple[Optional[str], Optional[str], str]:
    match = PAREN_NUM_RE.match(text)
    if match:
        token = match.group(1)
        remainder = normalize_space(match.group(2))
        return f"({token})", canonical_marker_token(token), remainder

    match = PAREN_ALPHA_RE.match(text)
    if match:
        token = match.group(1)
        remainder = normalize_space(match.group(2))
        return f"({token})", canonical_marker_token(token), remainder

    match = DOTTED_NUM_RE.match(text)
    if match:
        token = normalize_space(match.group(1)).replace(" ", "")
        remainder = normalize_space(match.group(2))
        return token, canonical_marker_token(token), remainder

    match = ALPHA_DOT_RE.match(text)
    if match:
        token = match.group(1)
        remainder = normalize_space(match.group(2))
        return f"{token}.", canonical_marker_token(token), remainder

    match = NUM_DOT_RE.match(text)
    if match:
        token = match.group(1)
        remainder = normalize_space(match.group(2))
        return f"{token}.", canonical_marker_token(token), remainder

    match = ROMAN_CLOSE_RE.match(text)
    if match:
        token = match.group(1)
        remainder = normalize_space(match.group(2))
        return f"{token})", canonical_marker_token(token), remainder

    match = BULLET_RE.match(text)
    if match:
        remainder = normalize_space(match.group(1))
        return "-", None, remainder

    return None, None, text


def make_segment_short_name(base_short_name: str, segment_title: str, index: int) -> str:
    if index == 0:
        return base_short_name

    lowered = segment_title.lower()
    if "additional act" in lowered:
        return f"{base_short_name}-additional-act"
    if "protocol" in lowered:
        return f"{base_short_name}-protocol"

    return f"{base_short_name}-part{index + 1}"


def prepare_preamble_lines(lines: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    for line in lines:
        text = normalize_space(line)
        if not text:
            continue
        if looks_like_date_line(text):
            continue
        cleaned.append(text)
    return cleaned


def marker_kind(block: Block) -> str:
    marker = block.marker_raw or ""
    token = block.marker_token or ""
    if not marker:
        return "none"

    if re.fullmatch(r"\([0-9]+\)", marker):
        return "numeric"

    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+(?:\([A-Za-z]+\))?", marker):
        return "dotted_numeric"

    if re.fullmatch(r"[0-9]+\.", marker):
        return "numeric"

    if re.fullmatch(r"\([A-Za-z]+\)", marker) or re.fullmatch(r"[A-Za-z]\.", marker):
        return "roman" if is_roman(token) else "alpha"

    if re.fullmatch(r"[ivxlcdm]+\)", marker, flags=re.IGNORECASE):
        return "roman"

    return "other"


def infer_block_depths(blocks: List[Block]) -> List[int]:
    """
    Infer list hierarchy for flat HTML where marker semantics carry structure.
    Keep explicit HTML list depth when available.
    """
    depths: List[int] = []
    flat_list_open = False
    prev_top_kind = "none"
    prev_top_text = ""

    for block in blocks:
        if block.depth > 0:
            depths.append(block.depth)
            continue

        kind = marker_kind(block)
        depth = 0

        if kind in {"alpha", "roman"}:
            if flat_list_open:
                depth = 1
            elif prev_top_kind in {"numeric", "dotted_numeric"} or prev_top_text.endswith(":"):
                depth = 1

        if depth > 0:
            flat_list_open = True
        else:
            flat_list_open = False
            prev_top_kind = kind
            prev_top_text = normalize_space(block.text)

        depths.append(depth)

    return depths


def build_segments(title: str, entries: List[Entry]) -> List[SegmentData]:
    segments: List[SegmentData] = [SegmentData(title=title)]
    current_segment = segments[0]
    current_article: Optional[ArticleData] = None

    current_container: Optional[ContainerHeading] = None
    container_by_key: Dict[str, ContainerHeading] = {}

    first_article_token: Optional[str] = None
    pending_split_title: Optional[str] = None

    for entry in entries:
        text = entry.text

        container = parse_container_heading(text)
        if container is not None:
            current_article = None
            if container.split_hint:
                pending_split_title = container.heading
            current_container = container
            if container.key not in container_by_key:
                container_by_key[container.key] = container
                current_segment.container_order.append(container)
            continue

        article_heading = parse_article_heading(text) if entry.is_bold_like else None
        if article_heading is not None:
            token, display_num, heading = article_heading

            should_split = (
                first_article_token is not None
                and token == first_article_token
                and len(current_segment.articles) > 0
            )
            if should_split:
                seg_title = pending_split_title or f"{title} Part {len(segments) + 1}"
                current_segment = SegmentData(title=seg_title)
                segments.append(current_segment)
                current_article = None
                current_container = None
                container_by_key = {}
                first_article_token = None
                pending_split_title = None

            if first_article_token is None:
                first_article_token = token

            container_key = current_container.key if current_container else None
            article = ArticleData(
                token=token,
                display_num=display_num,
                heading=heading,
                container_key=container_key,
            )
            current_segment.articles.append(article)
            current_article = article

            if current_container and current_container.key not in container_by_key:
                container_by_key[current_container.key] = current_container
                current_segment.container_order.append(current_container)
            continue

        if current_article is None:
            current_segment.pre_article_lines.append(text)
            continue

        marker_raw, marker_token, remainder = extract_marker(text)
        current_article.blocks.append(
            Block(
                raw_text=text,
                text=remainder,
                depth=entry.depth,
                marker_raw=marker_raw,
                marker_token=marker_token,
            )
        )

    return segments


def build_preamble(act_el: etree._Element, lines: Iterable[str]) -> int:
    preamble_lines = prepare_preamble_lines(lines)
    if not preamble_lines:
        return 0

    preamble_el = etree.SubElement(act_el, ns("preamble"))
    for idx, line in enumerate(preamble_lines, start=1):
        p_el = etree.SubElement(preamble_el, ns("p"), eId=f"preamble__p_{idx}")
        p_el.text = line

    return len(preamble_lines)


def make_meta(act_el: etree._Element, spec: TreatySpec, short_name: str, date_iso: str) -> None:
    work_uri = build_work_iri(spec.subtype, date_iso, short_name)
    expr_uri = f"{work_uri}/eng@{date_iso}"
    mani_uri = f"{expr_uri}.xml"

    meta_el = etree.SubElement(act_el, ns("meta"))

    identification_el = etree.SubElement(meta_el, ns("identification"), source="#wipo")

    frbr_work = etree.SubElement(identification_el, ns("FRBRWork"))
    etree.SubElement(frbr_work, ns("FRBRthis"), value=f"{work_uri}/!main")
    etree.SubElement(frbr_work, ns("FRBRuri"), value=work_uri)
    etree.SubElement(frbr_work, ns("FRBRdate"), date=date_iso, name="adoption")
    etree.SubElement(frbr_work, ns("FRBRauthor"), href="#wipo", **{"as": "#author"})
    etree.SubElement(frbr_work, ns("FRBRcountry"), value="un")
    etree.SubElement(frbr_work, ns("FRBRsubtype"), value=spec.subtype)
    etree.SubElement(frbr_work, ns("FRBRnumber"), value=short_name, showAs=short_name)

    frbr_expression = etree.SubElement(identification_el, ns("FRBRExpression"))
    etree.SubElement(frbr_expression, ns("FRBRthis"), value=f"{expr_uri}/!main")
    etree.SubElement(frbr_expression, ns("FRBRuri"), value=expr_uri)
    etree.SubElement(frbr_expression, ns("FRBRdate"), date=date_iso, name="adoption")
    etree.SubElement(frbr_expression, ns("FRBRauthor"), href="#wipo", **{"as": "#author"})
    etree.SubElement(frbr_expression, ns("FRBRlanguage"), language="eng")

    frbr_manifestation = etree.SubElement(identification_el, ns("FRBRManifestation"))
    etree.SubElement(frbr_manifestation, ns("FRBRthis"), value=f"{mani_uri}/!main")
    etree.SubElement(frbr_manifestation, ns("FRBRuri"), value=mani_uri)
    etree.SubElement(frbr_manifestation, ns("FRBRdate"), date=today_iso(), name="generation")
    etree.SubElement(frbr_manifestation, ns("FRBRauthor"), href="#johnbruene", **{"as": "#editor"})

    etree.SubElement(
        meta_el,
        ns("publication"),
        date=date_iso,
        name="officialPublication",
        showAs="WIPO publication",
    )

    references_el = etree.SubElement(meta_el, ns("references"), source="#wipo")
    etree.SubElement(
        references_el,
        ns("TLCOrganization"),
        eId="wipo",
        href="/ontology/organization/un/wipo",
        showAs="World Intellectual Property Organization",
    )
    etree.SubElement(
        references_el,
        ns("TLCPerson"),
        eId="johnbruene",
        href="/ontology/person/john-bruene",
        showAs="John Bruene",
    )


def make_preface(act_el: etree._Element, title: str) -> None:
    preface_el = etree.SubElement(act_el, ns("preface"))
    p_el = etree.SubElement(preface_el, ns("p"))
    doc_title_el = etree.SubElement(p_el, ns("docTitle"))
    doc_title_el.text = title


def create_text_container(parent: etree._Element, kind: str, text: str) -> None:
    if kind == "intro":
        intro_el = etree.SubElement(parent, ns("intro"))
        p_el = etree.SubElement(intro_el, ns("p"))
        p_el.text = text
    else:
        content_el = etree.SubElement(parent, ns("content"))
        p_el = etree.SubElement(content_el, ns("p"))
        p_el.text = text


def build_article(article_el: etree._Element, article: ArticleData) -> int:
    paragraph_count = 0

    blocks = article.blocks
    if not blocks:
        return paragraph_count

    inferred_depths = infer_block_depths(blocks)
    min_positive_depth = min((depth for depth in inferred_depths if depth > 0), default=1)
    rel_depths = [0 if depth == 0 else (depth - min_positive_depth + 1) for depth in inferred_depths]

    used_para_eids: set[str] = set()
    used_point_eids: set[str] = set()
    auto_para_counter = 0

    list_count_by_parent: Dict[str, int] = {}
    point_count_by_list: Dict[str, int] = {}

    active_list_by_depth: Dict[int, etree._Element] = {}
    list_parent_by_depth: Dict[int, etree._Element] = {}
    last_point_by_depth: Dict[int, etree._Element] = {}

    current_paragraph: Optional[etree._Element] = None

    article_eid = article_el.get("eId")
    assert article_eid is not None

    def new_para_eid() -> str:
        nonlocal auto_para_counter
        auto_para_counter += 1
        base = str(auto_para_counter)

        eid = f"{article_eid}__para_{base}"
        suffix = 2
        while eid in used_para_eids:
            eid = f"{article_eid}__para_{base}_{suffix}"
            suffix += 1
        used_para_eids.add(eid)
        return eid

    def ensure_paragraph_anchor() -> etree._Element:
        nonlocal current_paragraph, paragraph_count
        if current_paragraph is not None:
            return current_paragraph
        para_eid = new_para_eid()
        para_el = etree.SubElement(article_el, ns("paragraph"), eId=para_eid)
        paragraph_count += 1
        current_paragraph = para_el
        return para_el

    for idx, block in enumerate(blocks):
        depth = rel_depths[idx]
        next_depth = rel_depths[idx + 1] if idx + 1 < len(rel_depths) else 0
        has_nested = next_depth > depth

        text = normalize_space(block.text)

        if depth == 0:
            active_list_by_depth.clear()
            list_parent_by_depth.clear()
            last_point_by_depth.clear()

            para_eid = new_para_eid()
            para_el = etree.SubElement(article_el, ns("paragraph"), eId=para_eid)
            paragraph_count += 1

            if block.marker_raw:
                num_el = etree.SubElement(para_el, ns("num"))
                num_el.text = block.marker_raw

            if has_nested:
                if text:
                    create_text_container(para_el, "intro", text)
            else:
                create_text_container(para_el, "content", text)

            current_paragraph = para_el
            continue

        parent_item = ensure_paragraph_anchor() if depth == 1 else last_point_by_depth.get(depth - 1)
        if parent_item is None:
            parent_item = ensure_paragraph_anchor()

        parent_eid = parent_item.get("eId") or ""

        for key in [k for k in list(last_point_by_depth.keys()) if k > depth]:
            last_point_by_depth.pop(key, None)

        list_el = active_list_by_depth.get(depth)
        if list_el is None or list_parent_by_depth.get(depth) is not parent_item:
            list_index = list_count_by_parent.get(parent_eid, 0) + 1
            list_count_by_parent[parent_eid] = list_index
            list_eid = f"{parent_eid}__list_{list_index}"
            list_el = etree.SubElement(parent_item, ns("list"), eId=list_eid)
            active_list_by_depth[depth] = list_el
            list_parent_by_depth[depth] = parent_item

            for key in [k for k in list(active_list_by_depth.keys()) if k > depth]:
                active_list_by_depth.pop(key, None)
                list_parent_by_depth.pop(key, None)
                last_point_by_depth.pop(key, None)

        list_eid = list_el.get("eId") or ""

        if block.marker_token:
            point_base = block.marker_token
        else:
            point_index = point_count_by_list.get(list_eid, 0) + 1
            point_count_by_list[list_eid] = point_index
            point_base = str(point_index)

        point_eid = f"{list_eid}__point_{point_base}"
        suffix = 2
        while point_eid in used_point_eids:
            point_eid = f"{list_eid}__point_{point_base}_{suffix}"
            suffix += 1
        used_point_eids.add(point_eid)

        point_el = etree.SubElement(list_el, ns("point"), eId=point_eid)
        if block.marker_raw:
            num_el = etree.SubElement(point_el, ns("num"))
            num_el.text = block.marker_raw

        if has_nested:
            if text:
                create_text_container(point_el, "intro", text)
        else:
            create_text_container(point_el, "content", text)

        last_point_by_depth[depth] = point_el

    return paragraph_count


def extract_segment_source_text(title: str, segment: SegmentData) -> str:
    chunks: List[str] = [title]
    chunks.extend(prepare_preamble_lines(segment.pre_article_lines))

    container_map = {container.key: container for container in segment.container_order}
    last_container_key: Optional[str] = None

    for article in segment.articles:
        if article.container_key and article.container_key != last_container_key:
            container = container_map.get(article.container_key)
            if container is not None:
                chunks.append(f"{container.kind.upper()} {container.num}")
                if container.heading:
                    chunks.append(container.heading)
            last_container_key = article.container_key
        elif not article.container_key:
            last_container_key = None

        chunks.append(f"Article {article.display_num}")
        if article.heading:
            chunks.append(article.heading)
        for block in article.blocks:
            chunks.append(block.raw_text)
    return normalize_space(" ".join(chunks))


def extract_xml_text(root: etree._Element) -> str:
    chunks: List[str] = []
    for section in ("preface", "preamble", "body"):
        el = root.find(f".//{ns(section)}")
        if el is None:
            continue
        chunks.append(" ".join(t for t in el.itertext()))
    return normalize_space(" ".join(chunks))


def build_xml_for_segment(spec: TreatySpec, segment: SegmentData, short_name: str) -> Tuple[etree._ElementTree, Dict[str, int], str]:
    candidate_date_text = " ".join([segment.title] + segment.pre_article_lines[:8])
    date_iso = extract_date_from_text(candidate_date_text, fallback_year=spec.year)

    root = etree.Element(ns("akomaNtoso"), nsmap={None: AKN_NS})
    act_el = etree.SubElement(root, ns("act"), name=spec.subtype)

    make_meta(act_el, spec, short_name, date_iso)
    make_preface(act_el, segment.title)

    preamble_p_count = build_preamble(act_el, segment.pre_article_lines)

    body_el = etree.SubElement(act_el, ns("body"))

    article_count = 0
    paragraph_count = 0

    container_elements: Dict[str, etree._Element] = {}
    last_container_key: Optional[str] = None

    for article in segment.articles:
        parent = body_el

        if article.container_key:
            if article.container_key != last_container_key:
                container = next((c for c in segment.container_order if c.key == article.container_key), None)
                if container is not None:
                    container_el = etree.SubElement(
                        body_el,
                        ns(container.kind),
                        eId=f"{container.kind}_{make_slug(container.num)}",
                    )
                    num_el = etree.SubElement(container_el, ns("num"))
                    num_el.text = f"{container.kind.upper()} {container.num}"
                    if container.heading:
                        heading_el = etree.SubElement(container_el, ns("heading"))
                        heading_el.text = container.heading
                    container_elements[article.container_key] = container_el
                last_container_key = article.container_key
            parent = container_elements.get(article.container_key, body_el)
        else:
            last_container_key = None

        article_eid = f"art_{article.token}"
        article_el = etree.SubElement(parent, ns("article"), eId=article_eid)
        article_count += 1

        num_el = etree.SubElement(article_el, ns("num"))
        num_el.text = f"Article {article.display_num}"

        if article.heading:
            heading_el = etree.SubElement(article_el, ns("heading"))
            heading_el.text = article.heading

        paragraph_count += build_article(article_el, article)

    stats = {
        "articles": article_count,
        "paragraphs": paragraph_count,
        "preamble_paragraphs": preamble_p_count,
    }

    return etree.ElementTree(root), stats, date_iso


def parse_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 is None:
        return "Untitled WIPO Instrument"
    return normalize_space(h1.get_text(" ", strip=True))


def parse_info_lines(soup: BeautifulSoup) -> List[str]:
    lines: List[str] = []
    h1 = soup.find("h1")
    if h1 is None:
        return lines

    for sibling in h1.find_next_siblings():
        if getattr(sibling, "name", None) != "p":
            continue
        text = paragraph_inline_text(sibling)
        if not text:
            continue
        if parse_article_heading(text) is not None:
            break
        if looks_like_toc_heading(text):
            break
        lines.append(text)

    return lines


def parse_html_to_output_docs(html_path: Path, spec: TreatySpec) -> List[OutputDoc]:
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    title = parse_title(soup)
    entries = collect_entries(soup)

    segments = build_segments(title=title, entries=entries)

    output_docs: List[OutputDoc] = []
    for idx, segment in enumerate(segments):
        short_name = make_segment_short_name(spec.short_name, segment.title, idx)
        xml_tree, stats, date_iso = build_xml_for_segment(spec, segment, short_name)
        source_text = extract_segment_source_text(segment.title, segment)

        output_docs.append(
            OutputDoc(
                spec=spec,
                source_file=spec.input_file,
                short_name=short_name,
                date_iso=date_iso,
                year=int(date_iso[:4]),
                title=segment.title,
                xml_tree=xml_tree,
                text_source=source_text,
                stats=stats,
            )
        )

    return output_docs


def run(args: argparse.Namespace) -> int:
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    metadata_index: Path = args.metadata_index

    ensure_dir(output_dir)

    html_files = sorted(input_dir.glob("*.html"))
    if not html_files:
        print(f"No input HTML files found in {input_dir}", file=sys.stderr)
        return 1

    total_articles = 0
    total_paragraphs = 0
    total_preamble_ps = 0
    failed_safety: List[str] = []
    metadata_rows: List[Dict[str, str]] = []

    processed_count = 0

    for html_path in html_files:
        spec = TREATY_SPECS.get(html_path.name)
        if spec is None:
            print(f"SKIP {html_path.name}: not listed in authoritative treaty mapping")
            continue

        docs = parse_html_to_output_docs(html_path, spec)

        for doc in docs:
            file_name = output_file_name(doc.year, doc.short_name)
            out_path = output_dir / file_name
            doc.xml_tree.write(
                str(out_path),
                encoding="utf-8",
                xml_declaration=True,
                pretty_print=True,
            )

            xml_text = extract_xml_text(doc.xml_tree.getroot())
            similarity = compare_similarity(doc.text_source, xml_text)
            delta_pct = (1.0 - similarity) * 100.0

            status = "OK"
            if delta_pct > 1.0:
                status = "FAIL"
                failed_safety.append(file_name)

            processed_count += 1
            total_articles += doc.stats["articles"]
            total_paragraphs += doc.stats["paragraphs"]
            total_preamble_ps += doc.stats["preamble_paragraphs"]

            work_uri = build_work_iri(spec.subtype, doc.date_iso, doc.short_name)
            metadata_rows.append(
                {
                    "input_file": spec.input_file,
                    "output_file": file_name,
                    "short_name": doc.short_name,
                    "title": doc.title,
                    "subtype": spec.subtype,
                    "date": doc.date_iso,
                    "work_uri": work_uri,
                }
            )

            print(
                f"{status} {html_path.name} -> {file_name} | "
                f"articles={doc.stats['articles']} paragraphs={doc.stats['paragraphs']} "
                f"preamble_ps={doc.stats['preamble_paragraphs']} safety_delta={delta_pct:.2f}%"
            )

    json_dump(metadata_index, {"documents": metadata_rows})

    print(
        f"SUMMARY files={processed_count} articles={total_articles} "
        f"paragraphs={total_paragraphs} preamble_ps={total_preamble_ps} "
        f"safety_failures={len(failed_safety)}"
    )

    if failed_safety:
        print("Safety check failures:")
        for name in failed_safety:
            print(f" - {name}")
        return 2

    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
