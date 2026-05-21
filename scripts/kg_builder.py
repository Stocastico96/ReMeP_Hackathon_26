"""Build a legal knowledge graph (TTL) from the CSV benchmark dataset.

Run:
    uv run python -m scripts.kg_builder        # writes data/legal_kg.ttl
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

from scripts.akn_metadata import extract_frbr

EX      = Namespace("http://legal-kg.org/data/")
IPRONTO = Namespace("http://rhizomik.net/ontologies/2005/03/ipronto.owl#")
LEGAL   = Namespace("http://legal-kg.org/schema/")

CSV_PATH = Path("simplified_cq1_cq2_mock_dataset.csv")
TTL_PATH = Path("data/legal_kg.ttl")

# Map jurisdiction id (CSV column "id") → AKN local paths and display titles
_JURISDICTION_FILES: dict[str, dict[str, str]] = {
    "CA": {
        "local_path": "data/countries/ca/copyright/C-42.xml",
        "doc_title":  "Canadian Copyright Act",
    },
    "EU": {
        "local_path": "data/countries/eu/copyright/02006L0116-20111031.xml",
        "doc_title":  "EU Directive 2006/116/EC",
    },
    "FR": {
        "local_path": "data/countries/france/copyright/cpi_copyright_act.xml",
        "doc_title":  "French Code de la propriété intellectuelle",
    },
    "DE": {
        "local_path": "data/countries/germany/copyright/urhg_copyright_act.xml",
        "doc_title":  "German Urheberrechtsgesetz (UrhG)",
    },
    "IT": {
        "local_path": "data/countries/italy/copyright/19410716_041U0633_VIGENZA_20251218.xml",
        "doc_title":  "Italian Copyright Act (Law 633/1941)",
    },
    "NZ": {
        "local_path": "data/countries/nz/copyright/096be8ed81fe312e.xml",
        "doc_title":  "New Zealand Copyright Act 1994",
    },
    "CH": {
        "local_path": "data/countries/switzerland/copyright/urg_copyright_act.xml",
        "doc_title":  "Swiss Copyright Act (URG)",
    },
    "UK": {
        "local_path": "data/countries/uk/copyright/cdpa_1988.xml",
        "doc_title":  "Copyright, Designs and Patents Act 1988 (CDPA)",
    },
    "US": {
        "local_path": "data/countries/us/copyright/title17_copyright_act.xml",
        "doc_title":  "US Copyright Act (17 U.S.C.)",
    },
}


def build_kg(csv_path: Path = CSV_PATH) -> Graph:
    g = Graph()
    g.bind("ex",      EX)
    g.bind("ipronto", IPRONTO)
    g.bind("legal",   LEGAL)

    codes = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = row["id"].strip()
            codes.append(code)
            _add_duration_node(g, code, row)
            _add_rights_node(g, code, row)
            _add_exception_node(g, code, row)

    # Add Berne Convention baseline + compliance links
    wipo_node = _add_wipo_berne_node(g)
    for code in codes:
        dur_node = EX[f"{code}_duration"]
        years_vals = list(g.objects(dur_node, LEGAL.durationYears))
        if years_vals and int(str(years_vals[0])) >= 50:
            g.add((dur_node, LEGAL.compliesWith, wipo_node))

    return g


def _file_info(code: str) -> dict[str, str]:
    return _JURISDICTION_FILES.get(code, {"local_path": "", "doc_title": ""})


def _add_frbr_triples(g: Graph, node: URIRef, local_path: str) -> None:
    """Add authentic-source and point-in-time triples extracted from the AKN document."""
    meta = extract_frbr(local_path)
    if meta["frbr_work_uri"]:
        g.add((node, LEGAL.frbrWorkUri,    Literal(meta["frbr_work_uri"])))
    if meta["frbr_this"]:
        g.add((node, LEGAL.frbrThis,       Literal(meta["frbr_this"])))
    if meta["eli_uri"]:
        g.add((node, LEGAL.eliUri,         Literal(meta["eli_uri"])))
    if meta["point_in_time"]:
        g.add((node, LEGAL.pointInTime,    Literal(meta["point_in_time"], datatype=XSD.date)))
    if meta["date_in_force"]:
        g.add((node, LEGAL.dateInForce,    Literal(meta["date_in_force"], datatype=XSD.date)))
    g.add((node, LEGAL.isAuthoritative,    Literal(meta["is_authoritative"], datatype=XSD.boolean)))


def _add_duration_node(g: Graph, code: str, row: dict) -> None:
    node = EX[f"{code}_duration"]
    fi   = _file_info(code)

    g.add((node, RDF.type,                IPRONTO.ExploitationRight))
    g.add((node, LEGAL.jurisdiction,      Literal(code)))
    g.add((node, LEGAL.jurisdictionName,  Literal(row["name"])))
    g.add((node, LEGAL.ruleType,          Literal("copyright duration")))
    g.add((node, LEGAL.durationLiterary,  Literal(row["duration_literary"])))
    g.add((node, LEGAL.durationSoftware,  Literal(row["duration_software"])))
    g.add((node, LEGAL.localPath,         Literal(fi["local_path"])))
    g.add((node, LEGAL.docTitle,          Literal(fi["doc_title"])))

    art_ref = _infer_duration_article(code, row)
    if art_ref:
        g.add((node, LEGAL.articleRef, Literal(art_ref)))

    years = _extract_duration_years(row.get("duration_literary", ""))
    if years is not None:
        g.add((node, LEGAL.durationYears, Literal(years, datatype=XSD.integer)))

    dur_text = row.get("duration_literary", "").lower()
    if "pma" in dur_text or "death" in dur_text or "post mortem" in dur_text:
        g.add((node, IPRONTO.triggeredBy, Literal("death of author")))
    _add_frbr_triples(g, node, fi["local_path"])


def _add_rights_node(g: Graph, code: str, row: dict) -> None:
    node = EX[f"{code}_rights"]
    fi   = _file_info(code)

    g.add((node, RDF.type,               IPRONTO.ExploitationRight))
    g.add((node, LEGAL.jurisdiction,     Literal(code)))
    g.add((node, LEGAL.jurisdictionName, Literal(row["name"])))
    g.add((node, LEGAL.ruleType,         Literal("economic rights")))
    g.add((node, LEGAL.localPath,        Literal(fi["local_path"])))
    g.add((node, LEGAL.docTitle,         Literal(fi["doc_title"])))
    g.add((node, LEGAL.rightsNote,       Literal(row.get("rights_note", ""))))
    _add_frbr_triples(g, node, fi["local_path"])

    main_art = _RIGHTS_ARTICLES.get(code, "")
    if main_art:
        g.add((node, LEGAL.articleRef, Literal(main_art)))

    right_cols = {
        "reproduction": "reproduction_article",
        "distribution": "distribution_article",
        "communication": "communication_article",
        "rental":       "rental_article",
        "translation":  "translation_article",
    }
    for right, art_col in right_cols.items():
        if row.get(right, "").strip().lower() == "true":
            g.add((node, LEGAL.hasRight, Literal(right)))
            art_ref = row.get(art_col, "").strip()
            if art_ref and art_ref != "-":
                right_node = EX[f"{code}_right_{right}"]
                g.add((right_node, LEGAL.rightName, Literal(right)))
                g.add((right_node, LEGAL.articleRef, Literal(art_ref)))
                g.add((node, LEGAL.hasRightDetail, right_node))


def _add_exception_node(g: Graph, code: str, row: dict) -> None:
    node = EX[f"{code}_exception"]
    fi   = _file_info(code)
    exc  = row.get("private_copy_exception", "").strip()

    g.add((node, RDF.type,               IPRONTO.ExceptionsRight))
    g.add((node, LEGAL.jurisdiction,     Literal(code)))
    g.add((node, LEGAL.jurisdictionName, Literal(row["name"])))
    g.add((node, LEGAL.ruleType,         Literal("personal-use exception")))
    g.add((node, LEGAL.localPath,        Literal(fi["local_path"])))
    g.add((node, LEGAL.docTitle,         Literal(fi["doc_title"])))
    g.add((node, LEGAL.exceptionText,    Literal(exc)))

    has_exc = exc.lower().startswith("yes")
    g.add((node, LEGAL.hasException, Literal(has_exc, datatype=XSD.boolean)))

    _add_frbr_triples(g, node, fi["local_path"])

    # Extract article ref from "Yes (§ 53 UrhG)" style strings
    art_ref = _extract_article_from_exception(exc)
    if art_ref:
        g.add((node, LEGAL.articleRef, Literal(art_ref)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DURATION_ARTICLES: dict[str, str] = {
    "DE": "§ 64 UrhG",
    "UK": "s. 12 CDPA",
    "US": "§ 302 17 U.S.C.",
    "FR": "L123-1 CPI",
    "IT": "Art. 25 LDA",
    "CH": "Art. 29 URG",
    "EU": "Art. 1 Directive 2006/116",
    "CA": "s. 6 Copyright Act",
    "NZ": "s. 22 Copyright Act 1994",
}

# General economic/exploitation-rights article (top-level grant of rights)
_RIGHTS_ARTICLES: dict[str, str] = {
    "DE": "§ 15 UrhG",
    "UK": "s. 16 CDPA",
    "US": "§ 106 17 U.S.C.",
    "FR": "L122-1 CPI",
    "IT": "Art. 12 LDA",
    "CH": "Art. 10 URG",
    "EU": "Art. 2 InfoSoc Directive",
    "CA": "s. 3 Copyright Act",
    "NZ": "s. 16 Copyright Act 1994",
}


def _infer_duration_article(code: str, row: dict) -> str:
    return _DURATION_ARTICLES.get(code, "")


def _extract_duration_years(text: str) -> int | None:
    m = re.search(r"(\d+)\s*years?", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _add_wipo_berne_node(g: Graph) -> URIRef:
    """Add the Berne Convention Art. 7 baseline (50 years pma minimum)."""
    node = EX["WIPO_berne_art7"]
    g.add((node, RDF.type,               IPRONTO.ExploitationRight))
    g.add((node, LEGAL.jurisdiction,     Literal("WIPO")))
    g.add((node, LEGAL.jurisdictionName, Literal("WIPO (Berne Convention)")))
    g.add((node, LEGAL.ruleType,         Literal("copyright duration")))
    g.add((node, LEGAL.durationLiterary, Literal("50 years pma (minimum)")))
    g.add((node, LEGAL.durationYears,    Literal(50, datatype=XSD.integer)))
    g.add((node, LEGAL.articleRef,       Literal("Art. 7 Berne Convention")))
    g.add((node, LEGAL.docTitle,         Literal("Berne Convention for the Protection of Literary and Artistic Works")))
    g.add((node, IPRONTO.triggeredBy,    Literal("death of author")))
    return node


def _extract_article_from_exception(exc_text: str) -> str:
    """Extract '§ 53 UrhG' from 'Yes (§ 53 UrhG)'."""
    import re
    m = re.search(r"\((.+?)\)", exc_text)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    g = build_kg()
    TTL_PATH.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(TTL_PATH), format="turtle")
    print(f"KG written → {TTL_PATH}  ({len(g)} triples)")
