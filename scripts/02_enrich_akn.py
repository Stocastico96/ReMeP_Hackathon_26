#!/usr/bin/env python3
"""Enrich generated AKN XML with definitions and cross references."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from lxml import etree

from common import (
    AKN_NS,
    EXTERNAL_REFERENCE_ALIASES,
    article_ref_to_eid,
    compare_similarity,
    ensure_dir,
    make_slug,
    normalize_space,
)

NS = {"akn": AKN_NS}

DEF_RE = re.compile(
    r"[\"“]([^\"”]{2,140})[\"”]\s+(?:shall\s+mean|means|is\s+defined\s+as)\b",
    flags=re.IGNORECASE,
)

INTERNAL_REF_RE = re.compile(
    r"\bArticle(?:s)?\s+([0-9IVXLCDM]+(?:\s*(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies))?)(?:\s*\(([^)]+)\))?",
    flags=re.IGNORECASE,
)


@dataclass
class Span:
    start: int
    end: int
    kind: str
    payload: Dict[str, str]


@dataclass
class FileStats:
    defs_tagged: int = 0
    refs_internal: int = 0
    refs_external: int = 0
    safety_delta_pct: float = 0.0
    reverted: bool = False


def ns(tag: str) -> str:
    return f"{{{AKN_NS}}}{tag}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/wipo/akns"),
        help="Input directory containing base XML files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/wipo/akns_enriched"),
        help="Output directory for enriched XML files.",
    )
    parser.add_argument(
        "--metadata-index",
        type=Path,
        default=Path("data/wipo/akns/_metadata_index.json"),
        help="Metadata index from step 01.",
    )
    return parser.parse_args()


def append_text(parent: etree._Element, text: str) -> None:
    if not text:
        return
    if len(parent) == 0:
        parent.text = (parent.text or "") + text
    else:
        last = parent[-1]
        last.tail = (last.tail or "") + text


def append_child(parent: etree._Element, child: etree._Element) -> None:
    parent.append(child)


def extract_doc_text(root: etree._Element) -> str:
    chunks: List[str] = []
    for section in ("preface", "preamble", "body"):
        el = root.find(f".//{ns(section)}")
        if el is None:
            continue
        chunks.append(" ".join(el.itertext()))
    return normalize_space(" ".join(chunks))


def load_work_uri_map(input_dir: Path, metadata_index: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    if metadata_index.exists():
        data = etree.parse(str(metadata_index)) if metadata_index.suffix == ".xml" else None
        if data is None:
            import json

            payload = json.loads(metadata_index.read_text(encoding="utf-8"))
            for item in payload.get("documents", []):
                short_name = item.get("short_name")
                work_uri = item.get("work_uri")
                if short_name and work_uri:
                    mapping[short_name] = work_uri

    if mapping:
        return mapping

    for xml_path in sorted(input_dir.glob("*.xml")):
        try:
            root = etree.parse(str(xml_path)).getroot()
        except Exception:
            continue
        frbr_uri = root.find(".//akn:FRBRWork/akn:FRBRuri", namespaces=NS)
        work_uri = frbr_uri.get("value") if frbr_uri is not None else None
        if not work_uri:
            continue
        short_name = work_uri.rstrip("/").split("/")[-1]
        mapping[short_name] = work_uri

    return mapping


def make_alias_patterns(work_uri_map: Dict[str, str]) -> List[Tuple[re.Pattern, str]]:
    pairs: List[Tuple[str, str]] = []
    for alias, short_name in EXTERNAL_REFERENCE_ALIASES.items():
        work_uri = work_uri_map.get(short_name)
        if work_uri:
            pairs.append((alias, work_uri))

    pairs.sort(key=lambda item: len(item[0]), reverse=True)

    patterns: List[Tuple[re.Pattern, str]] = []
    for alias, href in pairs:
        pattern = re.compile(rf"(?<![\w/]){re.escape(alias)}(?![\w-])", flags=re.IGNORECASE)
        patterns.append((pattern, href))

    return patterns


def collect_internal_targets(root: etree._Element) -> Set[str]:
    out: Set[str] = set()
    for el in root.iter():
        eid = el.get("eId")
        if eid:
            out.add(eid)
    return out


def pick_spans(spans: List[Span]) -> List[Span]:
    priority = {"def": 0, "ref_internal": 1, "ref_external": 2}
    spans.sort(key=lambda s: (s.start, -(s.end - s.start), priority.get(s.kind, 99)))

    accepted: List[Span] = []
    cursor = -1
    for span in spans:
        if span.start < cursor:
            continue
        accepted.append(span)
        cursor = span.end
    return accepted


def transform_paragraph(
    p_el: etree._Element,
    eid_set: Set[str],
    alias_patterns: List[Tuple[re.Pattern, str]],
    term_registry: Dict[str, Tuple[str, str]],
    def_counter: Dict[str, int],
    stats: FileStats,
) -> None:
    raw_text = "".join(p_el.itertext())
    if not raw_text.strip():
        return

    spans: List[Span] = []

    for match in DEF_RE.finditer(raw_text):
        term = normalize_space(match.group(1)).strip("“”\"")
        if not term:
            continue
        start, end = match.span(1)
        spans.append(Span(start=start, end=end, kind="def", payload={"term": term}))

    for match in INTERNAL_REF_RE.finditer(raw_text):
        article_token = match.group(1)
        para_token = match.group(2)

        art_eid = article_ref_to_eid(article_token)
        href = f"#{art_eid}"

        if para_token:
            para_eid = article_ref_to_eid(article_token, para_token)
            if para_eid in eid_set:
                href = f"#{para_eid}"
            elif art_eid not in eid_set:
                continue
        elif art_eid not in eid_set:
            continue

        spans.append(
            Span(
                start=match.start(),
                end=match.end(),
                kind="ref_internal",
                payload={"href": href},
            )
        )

    for pattern, href in alias_patterns:
        for match in pattern.finditer(raw_text):
            spans.append(
                Span(
                    start=match.start(),
                    end=match.end(),
                    kind="ref_external",
                    payload={"href": href},
                )
            )

    accepted = pick_spans(spans)
    if not accepted:
        return

    for child in list(p_el):
        p_el.remove(child)
    p_el.text = None

    cursor = 0

    for span in accepted:
        if span.start > cursor:
            append_text(p_el, raw_text[cursor:span.start])

        selected_text = raw_text[span.start : span.end]

        if span.kind == "def":
            term_text = span.payload["term"]
            term_key = term_text.casefold()
            if term_key not in term_registry:
                slug = make_slug(term_text) or "term"
                term_eid = f"term_{slug}"
                term_registry[term_key] = (term_eid, term_text)

            term_eid, _ = term_registry[term_key]
            def_index = def_counter.get(term_eid, 0) + 1
            def_counter[term_eid] = def_index
            def_eid = f"def_{term_eid}_{def_index}"

            def_el = etree.Element(ns("def"), eId=def_eid, refersTo=f"#{term_eid}")
            def_el.text = selected_text
            append_child(p_el, def_el)
            stats.defs_tagged += 1

        else:
            href = span.payload["href"]
            ref_el = etree.Element(ns("ref"), href=href)
            ref_el.text = selected_text
            append_child(p_el, ref_el)
            if span.kind == "ref_internal":
                stats.refs_internal += 1
            else:
                stats.refs_external += 1

        cursor = span.end

    if cursor < len(raw_text):
        append_text(p_el, raw_text[cursor:])


def ensure_references(root: etree._Element) -> etree._Element:
    meta_el = root.find(".//akn:meta", namespaces=NS)
    if meta_el is None:
        act_el = root.find(".//akn:act", namespaces=NS)
        if act_el is None:
            raise ValueError("AKN document is missing <act> root child.")
        meta_el = etree.SubElement(act_el, ns("meta"))

    references_el = meta_el.find("akn:references", namespaces=NS)
    if references_el is None:
        references_el = etree.SubElement(meta_el, ns("references"), source="#wipo")

    if references_el.get("source") != "#wipo":
        references_el.set("source", "#wipo")

    return references_el


def upsert_tlc_terms(references_el: etree._Element, term_registry: Dict[str, Tuple[str, str]]) -> int:
    existing_ids = {el.get("eId") for el in references_el.findall("akn:TLCTerm", namespaces=NS)}
    added = 0

    for _, (term_eid, term_text) in term_registry.items():
        if term_eid in existing_ids:
            continue
        slug = make_slug(term_text) or "term"
        etree.SubElement(
            references_el,
            ns("TLCTerm"),
            eId=term_eid,
            href=f"/ontology/term/{slug}",
            showAs=term_text,
        )
        existing_ids.add(term_eid)
        added += 1

    return added


def enrich_xml_file(
    xml_path: Path,
    output_path: Path,
    alias_patterns: List[Tuple[re.Pattern, str]],
) -> FileStats:
    stats = FileStats()

    original_bytes = xml_path.read_bytes()
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    before_text = extract_doc_text(root)
    eid_set = collect_internal_targets(root)

    term_registry: Dict[str, Tuple[str, str]] = {}
    def_counter: Dict[str, int] = {}

    for term_el in root.findall(".//akn:references/akn:TLCTerm", namespaces=NS):
        term_eid = term_el.get("eId")
        show_as = term_el.get("showAs")
        if term_eid and show_as:
            term_registry[show_as.casefold()] = (term_eid, show_as)

    paragraph_nodes = root.findall(".//akn:body//akn:p", namespaces=NS)
    paragraph_nodes += root.findall(".//akn:preamble//akn:p", namespaces=NS)

    for p_el in paragraph_nodes:
        transform_paragraph(
            p_el=p_el,
            eid_set=eid_set,
            alias_patterns=alias_patterns,
            term_registry=term_registry,
            def_counter=def_counter,
            stats=stats,
        )

    references_el = ensure_references(root)
    upsert_tlc_terms(references_el, term_registry)

    after_text = extract_doc_text(root)
    similarity = compare_similarity(before_text, after_text)
    stats.safety_delta_pct = (1.0 - similarity) * 100.0

    if stats.safety_delta_pct > 1.0:
        output_path.write_bytes(original_bytes)
        stats.reverted = True
        return stats

    tree.write(str(output_path), encoding="utf-8", xml_declaration=True, pretty_print=True)
    return stats


def run(args: argparse.Namespace) -> int:
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    metadata_index: Path = args.metadata_index

    ensure_dir(output_dir)

    xml_files = sorted(
        path
        for path in input_dir.glob("*.xml")
        if not path.name.startswith("_")
    )
    if not xml_files:
        print(f"No input XML files found in {input_dir}", file=sys.stderr)
        return 1

    work_uri_map = load_work_uri_map(input_dir=input_dir, metadata_index=metadata_index)
    alias_patterns = make_alias_patterns(work_uri_map)

    total_defs = 0
    total_refs_internal = 0
    total_refs_external = 0
    reverted_files: List[str] = []

    for xml_path in xml_files:
        out_path = output_dir / xml_path.name
        stats = enrich_xml_file(xml_path, out_path, alias_patterns)

        total_defs += stats.defs_tagged
        total_refs_internal += stats.refs_internal
        total_refs_external += stats.refs_external

        status = "OK"
        if stats.reverted:
            status = "REVERTED"
            reverted_files.append(xml_path.name)

        print(
            f"{status} {xml_path.name} -> {out_path.name} | "
            f"defs={stats.defs_tagged} refs_internal={stats.refs_internal} "
            f"refs_external={stats.refs_external} safety_delta={stats.safety_delta_pct:.2f}%"
        )

    print(
        f"SUMMARY files={len(xml_files)} defs_tagged={total_defs} "
        f"refs_internal={total_refs_internal} refs_external={total_refs_external} "
        f"safety_reverted={len(reverted_files)}"
    )

    if reverted_files:
        print("Reverted files:")
        for name in reverted_files:
            print(f" - {name}")
        return 2

    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
