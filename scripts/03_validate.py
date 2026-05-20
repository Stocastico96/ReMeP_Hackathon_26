#!/usr/bin/env python3
"""Validate enriched AKN XML files against schema and project quality checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

from lxml import etree

from common import AKN_NS, ensure_dir, normalize_space

NS = {"akn": AKN_NS}

WORK_URI_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+$")
WORK_THIS_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+/!main$")
EXPR_URI_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+/eng@\d{4}-\d{2}-\d{2}$")
EXPR_THIS_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+/eng@\d{4}-\d{2}-\d{2}/!main$")
MANI_URI_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+/eng@\d{4}-\d{2}-\d{2}\.xml$")
MANI_THIS_RE = re.compile(r"^/akn/un/act/[a-zA-Z0-9-]+/wipo/\d{4}-\d{2}-\d{2}/[a-z0-9-]+/eng@\d{4}-\d{2}-\d{2}\.xml/!main$")

XML_XSD_FALLBACK = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<xs:schema targetNamespace=\"http://www.w3.org/XML/1998/namespace\"
           xmlns:xs=\"http://www.w3.org/2001/XMLSchema\"
           xmlns:xml=\"http://www.w3.org/XML/1998/namespace\"
           elementFormDefault=\"qualified\"
           attributeFormDefault=\"unqualified\">
  <xs:attribute name=\"base\" type=\"xs:anyURI\"/>
  <xs:attribute name=\"id\" type=\"xs:ID\"/>
  <xs:attribute name=\"lang\">
    <xs:simpleType>
      <xs:restriction base=\"xs:language\">
        <xs:pattern value=\"[a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})*\"/>
      </xs:restriction>
    </xs:simpleType>
  </xs:attribute>
  <xs:attribute name=\"space\">
    <xs:simpleType>
      <xs:restriction base=\"xs:NCName\">
        <xs:enumeration value=\"default\"/>
        <xs:enumeration value=\"preserve\"/>
      </xs:restriction>
    </xs:simpleType>
  </xs:attribute>
  <xs:attributeGroup name=\"specialAttrs\">
    <xs:attribute ref=\"xml:base\"/>
    <xs:attribute ref=\"xml:lang\"/>
    <xs:attribute ref=\"xml:space\"/>
    <xs:attribute ref=\"xml:id\"/>
  </xs:attributeGroup>
</xs:schema>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/wipo/akns_enriched"),
        help="Directory containing enriched XML files.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("doc/akomantoso30.xsd"),
        help="AKN 3.0 XSD path.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/wipo/validation_report.json"),
        help="JSON validation report output path.",
    )
    return parser.parse_args()


def ensure_xml_xsd(schema_path: Path) -> None:
    xml_xsd_path = schema_path.parent / "xml.xsd"
    if xml_xsd_path.exists():
        return
    xml_xsd_path.write_text(XML_XSD_FALLBACK, encoding="utf-8")


def load_schema(schema_path: Path) -> etree.XMLSchema:
    ensure_xml_xsd(schema_path)
    schema_doc = etree.parse(str(schema_path))
    return etree.XMLSchema(schema_doc)


def collect_eids(root: etree._Element) -> Dict[str, List[str]]:
    eids: Dict[str, List[str]] = {}
    for el in root.iter():
        eid = el.get("eId")
        if not eid:
            continue
        eids.setdefault(eid, []).append(el.tag)
    return eids


def validate_refs(root: etree._Element, eid_set: Set[str]) -> List[str]:
    missing: List[str] = []
    for ref_el in root.findall(".//akn:ref", namespaces=NS):
        href = ref_el.get("href")
        if not href or not href.startswith("#"):
            continue
        target = href[1:]
        if target not in eid_set:
            missing.append(href)
    return sorted(set(missing))


def validate_def_terms(root: etree._Element) -> List[str]:
    term_ids = {
        term_el.get("eId")
        for term_el in root.findall(".//akn:references/akn:TLCTerm", namespaces=NS)
        if term_el.get("eId")
    }

    missing: List[str] = []
    for def_el in root.findall(".//akn:def", namespaces=NS):
        def_id = def_el.get("eId") or "(no-eId)"
        refers_to = def_el.get("refersTo")
        if not refers_to or not refers_to.startswith("#"):
            missing.append(def_id)
            continue
        term_id = refers_to[1:]
        if term_id not in term_ids:
            missing.append(def_id)

    return missing


def validate_frbr(root: etree._Element) -> List[str]:
    issues: List[str] = []

    def get_value(path: str) -> str:
        el = root.find(path, namespaces=NS)
        return el.get("value") if el is not None and el.get("value") else ""

    work_uri = get_value(".//akn:FRBRWork/akn:FRBRuri")
    work_this = get_value(".//akn:FRBRWork/akn:FRBRthis")
    expr_uri = get_value(".//akn:FRBRExpression/akn:FRBRuri")
    expr_this = get_value(".//akn:FRBRExpression/akn:FRBRthis")
    mani_uri = get_value(".//akn:FRBRManifestation/akn:FRBRuri")
    mani_this = get_value(".//akn:FRBRManifestation/akn:FRBRthis")

    if not WORK_URI_RE.match(work_uri):
        issues.append("FRBRWork/FRBRuri format invalid")
    if not WORK_THIS_RE.match(work_this):
        issues.append("FRBRWork/FRBRthis format invalid")
    if not EXPR_URI_RE.match(expr_uri):
        issues.append("FRBRExpression/FRBRuri format invalid")
    if not EXPR_THIS_RE.match(expr_this):
        issues.append("FRBRExpression/FRBRthis format invalid")
    if not MANI_URI_RE.match(mani_uri):
        issues.append("FRBRManifestation/FRBRuri format invalid")
    if not MANI_THIS_RE.match(mani_this):
        issues.append("FRBRManifestation/FRBRthis format invalid")

    if work_this and work_uri and work_this != f"{work_uri}/!main":
        issues.append("FRBRWork/FRBRthis must equal FRBRWork/FRBRuri + '/!main'")
    if expr_this and expr_uri and expr_this != f"{expr_uri}/!main":
        issues.append("FRBRExpression/FRBRthis must equal FRBRExpression/FRBRuri + '/!main'")
    if mani_this and mani_uri and mani_this != f"{mani_uri}/!main":
        issues.append("FRBRManifestation/FRBRthis must equal FRBRManifestation/FRBRuri + '/!main'")

    country_el = root.find(".//akn:FRBRWork/akn:FRBRcountry", namespaces=NS)
    if country_el is None or country_el.get("value") != "un":
        issues.append("FRBRcountry must be 'un'")

    author_el = root.find(".//akn:FRBRWork/akn:FRBRauthor", namespaces=NS)
    if author_el is None:
        issues.append("FRBRWork/FRBRauthor missing")
    else:
        if author_el.get("href") != "#wipo":
            issues.append("FRBRWork/FRBRauthor@href should be #wipo")
        if author_el.get("as") != "#author":
            issues.append("FRBRWork/FRBRauthor@as should be #author")

    expr_author = root.find(".//akn:FRBRExpression/akn:FRBRauthor", namespaces=NS)
    if expr_author is None:
        issues.append("FRBRExpression/FRBRauthor missing")
    else:
        if expr_author.get("href") != "#wipo":
            issues.append("FRBRExpression/FRBRauthor@href should be #wipo")
        if expr_author.get("as") != "#author":
            issues.append("FRBRExpression/FRBRauthor@as should be #author")

    mani_author = root.find(".//akn:FRBRManifestation/akn:FRBRauthor", namespaces=NS)
    if mani_author is None:
        issues.append("FRBRManifestation/FRBRauthor missing")
    else:
        if mani_author.get("href") != "#johnbruene":
            issues.append("FRBRManifestation/FRBRauthor@href should be #johnbruene")
        if mani_author.get("as") != "#editor":
            issues.append("FRBRManifestation/FRBRauthor@as should be #editor")

    identification_el = root.find(".//akn:meta/akn:identification", namespaces=NS)
    if identification_el is None:
        issues.append("meta/identification missing")
    elif identification_el.get("source") != "#wipo":
        issues.append("meta/identification@source should be #wipo")

    references_el = root.find(".//akn:meta/akn:references", namespaces=NS)
    if references_el is None:
        issues.append("meta/references missing")
    elif references_el.get("source") != "#wipo":
        issues.append("meta/references@source should be #wipo")

    publication_el = root.find(".//akn:meta/akn:publication", namespaces=NS)
    if publication_el is None:
        issues.append("meta/publication missing")

    return issues


def validate_file(xml_path: Path, schema: etree.XMLSchema) -> Dict[str, object]:
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    schema_valid = schema.validate(tree)
    schema_errors = [str(err) for err in schema.error_log] if not schema_valid else []

    eids = collect_eids(root)
    duplicate_eids = sorted([eid for eid, tags in eids.items() if len(tags) > 1])
    eid_set = set(eids)

    missing_ref_targets = validate_refs(root, eid_set)
    missing_def_terms = validate_def_terms(root)
    frbr_issues = validate_frbr(root)

    para_unmarked = [eid for eid in eid_set if "para_unmarked" in eid]

    overall_valid = (
        schema_valid
        and not duplicate_eids
        and not missing_ref_targets
        and not missing_def_terms
        and not frbr_issues
        and not para_unmarked
    )

    return {
        "file": xml_path.name,
        "schema_valid": schema_valid,
        "schema_errors": schema_errors,
        "duplicate_eids": duplicate_eids,
        "missing_internal_ref_targets": missing_ref_targets,
        "defs_missing_tlcterm": missing_def_terms,
        "frbr_issues": frbr_issues,
        "para_unmarked_eids": para_unmarked,
        "overall_valid": overall_valid,
    }


def run(args: argparse.Namespace) -> int:
    input_dir: Path = args.input_dir
    schema_path: Path = args.schema
    report_path: Path = args.report

    xml_files = sorted(path for path in input_dir.glob("*.xml") if not path.name.startswith("_"))
    if not xml_files:
        print(f"No input XML files found in {input_dir}", file=sys.stderr)
        return 1

    schema = load_schema(schema_path)

    results: List[Dict[str, object]] = []
    invalid = 0

    for xml_path in xml_files:
        result = validate_file(xml_path, schema)
        results.append(result)

        status = "PASS" if result["overall_valid"] else "FAIL"
        if status == "FAIL":
            invalid += 1

        print(
            f"{status} {xml_path.name} | "
            f"schema={result['schema_valid']} dup_eid={len(result['duplicate_eids'])} "
            f"missing_ref={len(result['missing_internal_ref_targets'])} "
            f"missing_term={len(result['defs_missing_tlcterm'])} "
            f"frbr={len(result['frbr_issues'])} para_unmarked={len(result['para_unmarked_eids'])}"
        )

    summary = {
        "total_files": len(results),
        "valid_files": len(results) - invalid,
        "invalid_files": invalid,
    }

    ensure_dir(report_path.parent)
    report_path.write_text(
        json.dumps({"summary": summary, "files": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"SUMMARY total={summary['total_files']} valid={summary['valid_files']} "
        f"invalid={summary['invalid_files']} report={report_path}"
    )

    return 0 if invalid == 0 else 2


def main() -> None:
    args = parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
