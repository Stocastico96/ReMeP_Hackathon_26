"""Query the legal KG and return a KGEvidence payload.

On first call the KG is built from the CSV (if TTL doesn't exist) and cached
in memory.  Subsequent calls reuse the in-memory graph.
"""

from __future__ import annotations

import threading
from pathlib import Path

from rdflib import Graph

from scripts.article_locator import find_eid
from scripts.kg_builder import build_kg, TTL_PATH, CSV_PATH, EX, LEGAL
from scripts.mock_kg_evidence import KGEvidence, NormalizedRule, DocumentRef, AKNReference, get_mock_evidence
from scripts.pydantic_models import SPARQLParams, JURISDICTION_CODE
from scripts.sparql_generator import generate_sparql
from scripts._akn_passage import extract_passage

_graph: Graph | None = None
_lock = threading.Lock()


def _get_graph() -> Graph:
    global _graph
    if _graph is not None:
        return _graph
    with _lock:
        if _graph is not None:
            return _graph
        if TTL_PATH.exists():
            g = Graph()
            g.parse(str(TTL_PATH), format="turtle")
        else:
            g = build_kg(CSV_PATH)
            TTL_PATH.parent.mkdir(parents=True, exist_ok=True)
            g.serialize(destination=str(TTL_PATH), format="turtle")
        _graph = g
    return _graph


def query_kg(params: SPARQLParams) -> KGEvidence:
    """Execute SPARQL over the legal KG and return a KGEvidence dict.

    Falls back to mock data for WIPO / unknown jurisdictions not in the CSV.
    """
    # Normalize generic topics first so jurisdiction routing uses the right topic
    if params.rule_type in ("copyright", "intellectual property"):
        params = params.model_copy(update={"rule_type": "economic rights", "rule_key": "rights"})

    # Unknown jurisdiction → default to WIPO (Berne Convention baseline)
    if not params.jurisdiction_code:
        params = params.model_copy(update={"jurisdiction_name": "WIPO", "jurisdiction_code": "WIPO"})

    # WIPO has no CSV rows — use mock which has Berne Convention data
    if params.jurisdiction_code == "WIPO":
        return get_mock_evidence(params.rule_type, "WIPO")

    g      = _get_graph()
    sparql = generate_sparql(params)
    results = list(g.query(sparql))

    if not results:
        return get_mock_evidence(params.rule_type, params.jurisdiction_name)

    if params.rule_type == "copyright duration":
        return _map_duration(results[0], params)
    if params.rule_type == "economic rights":
        return _map_rights(results, params)
    if params.rule_type == "personal-use exception":
        return _map_exception(results[0], params)

    return get_mock_evidence(params.rule_type, params.jurisdiction_name)


def _source_url(node) -> str:
    """The publisher URL stored on a KG node, empty when the node is unknown."""
    if node is None:
        return ""
    return str(next(iter(_get_graph().objects(node, LEGAL.sourceUrl)), ""))


# ---------------------------------------------------------------------------
# Result mappers
# ---------------------------------------------------------------------------

def _str(val) -> str:
    return str(val) if val is not None else ""


def _map_duration(row, params: SPARQLParams) -> KGEvidence:
    duration_literary = _str(row.durationLiterary)
    article_ref       = _str(getattr(row, "articleRef", None))
    local_path        = _str(row.localPath)
    doc_title         = _str(row.docTitle)
    jurisdiction_name = _str(row.jurisdictionName)

    # Look up eId from article ref in the AKN XML
    eid = find_eid(local_path, article_ref) if article_ref else ""

    # Extract actual passage from the AKN XML element
    jname = jurisdiction_name or params.jurisdiction_name
    passage = extract_passage(local_path, eid)
    if not passage:
        passage = f"Copyright protection in {jname} lasts {duration_literary}."
    span = _pick_span(passage, duration_literary)

    return KGEvidence(
        answer_candidate=f"Copyright protection in {jname} lasts {duration_literary}.",
        rule_type="copyright duration",
        normalized_rule=NormalizedRule(value=_normalize_duration(duration_literary), unit="years"),
        document=DocumentRef(title=doc_title, uri=local_path, local_path=local_path,
                             source_url=_source_url(getattr(row, "node", None))),
        reference=AKNReference(article=article_ref, eid=eid),
        passage=passage,
        supporting_span=span,
    )


def _map_rights(rows, params: SPARQLParams) -> KGEvidence:
    if not rows:
        return _empty(params)

    row           = rows[0]
    local_path    = _str(row.localPath)
    doc_title     = _str(row.docTitle)
    jurisdiction_name = _str(row.jurisdictionName)
    rights_note   = _str(getattr(row, "rightsNote", None))

    rights = sorted({_str(r.right) for r in rows if r.right})

    # For economic rights, show the first right's article ref
    article_ref = _str(getattr(rows[0], "articleRef", None))
    eid = find_eid(local_path, article_ref) if article_ref else ""

    jname       = jurisdiction_name or params.jurisdiction_name
    rights_list = ", ".join(rights)
    passage = extract_passage(local_path, eid)
    if not passage:
        passage = (
            f"{jname} grants the following exclusive economic rights: {rights_list}. "
            + (rights_note if rights_note else "")
        ).strip()

    # Find an exclusive-right phrase in the passage (EN or IT) to use as span
    import re as _re
    span_match = _re.search(
        r"(exclusive right|diritto esclusivo|ausschließliche[s]? Recht|droit exclusif)[^.\n]{0,80}",
        passage, _re.IGNORECASE,
    )
    span = span_match.group(0).strip() if span_match else ""

    return KGEvidence(
        answer_candidate=f"{jname} grants: {rights_list}.",
        rule_type="economic rights",
        normalized_rule=NormalizedRule(value="list"),
        document=DocumentRef(title=doc_title, uri=local_path, local_path=local_path,
                             source_url=_source_url(getattr(row, "node", None))),
        reference=AKNReference(article=article_ref, eid=eid),
        passage=passage,
        supporting_span=span,
    )


def _map_exception(row, params: SPARQLParams) -> KGEvidence:
    has_exc   = str(row.hasException).lower() == "true"
    exc_text  = _str(row.exceptionText)
    local_path = _str(row.localPath)
    doc_title  = _str(row.docTitle)
    jurisdiction_name = _str(row.jurisdictionName)
    article_ref = _str(getattr(row, "articleRef", None))

    eid = find_eid(local_path, article_ref) if article_ref else ""

    jname   = jurisdiction_name or params.jurisdiction_name
    yn      = "Yes" if has_exc else "No"
    passage = extract_passage(local_path, eid)
    if not passage:
        passage = f"{jname} private-copy exception: {exc_text}"
    span    = exc_text

    return KGEvidence(
        answer_candidate=f"{yn}, {jname} {'has' if has_exc else 'does not have'} a private-copy exception. {exc_text}",
        rule_type="personal-use exception",
        normalized_rule=NormalizedRule(value="yes" if has_exc else "no"),
        document=DocumentRef(title=doc_title, uri=local_path, local_path=local_path,
                             source_url=_source_url(getattr(row, "node", None))),
        reference=AKNReference(article=article_ref, eid=eid),
        passage=passage,
        supporting_span=span,
    )


def _empty(params: SPARQLParams) -> KGEvidence:
    return KGEvidence(
        answer_candidate="",
        rule_type=params.rule_type,
        normalized_rule=NormalizedRule(),
        document=DocumentRef(title="", uri="", local_path=""),
        reference=AKNReference(),
        passage="",
        supporting_span="",
    )


# ---------------------------------------------------------------------------
# Duration normalizer
# ---------------------------------------------------------------------------

def _normalize_duration(text: str) -> str:
    t = text.lower()
    if "70" in t:
        return "life_plus_70"
    if "50" in t:
        return "life_plus_50"
    return text


# ---------------------------------------------------------------------------
# Compliance check
# ---------------------------------------------------------------------------

_ALL_COUNTRIES: dict[str, str] = {
    "DE": "Germany",
    "UK": "United Kingdom",
    "US": "United States",
    "FR": "France",
    "IT": "Italy",
    "CH": "Switzerland",
    "EU": "European Union",
    "CA": "Canada",
    "NZ": "New Zealand",
}


def check_compliance(country_code: str) -> dict:
    """Return compliance data for *country_code* vs Berne Convention Art. 7.

    Returns a dict with country info, treaty info, and compliance verdict.
    Falls back gracefully if the country is not in the KG.
    """
    g = _get_graph()

    # Fetch country duration node
    country_node = EX[f"{country_code}_duration"]
    country_triples = {
        "name":    next(iter(g.objects(country_node, LEGAL.jurisdictionName)), None),
        "years":   next(iter(g.objects(country_node, LEGAL.durationYears)),    None),
        "text":    next(iter(g.objects(country_node, LEGAL.durationLiterary)), None),
        "article": next(iter(g.objects(country_node, LEGAL.articleRef)),       None),
        "path":    next(iter(g.objects(country_node, LEGAL.localPath)),        None),
        "title":   next(iter(g.objects(country_node, LEGAL.docTitle)),         None),
    }

    # Fetch WIPO Berne baseline
    wipo_node  = EX["WIPO_berne_art7"]
    wipo_years_val = next(iter(g.objects(wipo_node, LEGAL.durationYears)), None)
    wipo_article   = str(next(iter(g.objects(wipo_node, LEGAL.articleRef)), "Art. 7 Berne Convention"))
    wipo_name      = str(next(iter(g.objects(wipo_node, LEGAL.jurisdictionName)), "WIPO (Berne Convention)"))

    country_years_val = country_triples["years"]
    if country_years_val is None or wipo_years_val is None:
        return {"error": f"No duration data found for {country_code}"}

    country_years = int(str(country_years_val))
    wipo_years    = int(str(wipo_years_val))
    compliant     = country_years >= wipo_years
    margin        = country_years - wipo_years

    country_name    = str(country_triples["name"])  if country_triples["name"]    else _ALL_COUNTRIES.get(country_code, country_code)
    country_text    = str(country_triples["text"])  if country_triples["text"]    else f"{country_years} years pma"
    country_article = str(country_triples["article"]) if country_triples["article"] else ""
    local_path      = str(country_triples["path"])  if country_triples["path"]    else ""
    doc_title       = str(country_triples["title"]) if country_triples["title"]   else ""

    # Load AKN passage for the duration article
    eid     = find_eid(local_path, country_article) if country_article else ""
    passage = extract_passage(local_path, eid) if eid else ""

    source_url = str(next(iter(g.objects(country_node, LEGAL.sourceUrl)), ""))

    return {
        "country_code":          country_code,
        "country_name":          country_name,
        "country_duration_years": country_years,
        "country_duration_text": country_text,
        "country_article":       country_article,
        "country_triggered_by":  "death of author",
        "treaty_name":           wipo_name,
        "treaty_duration_years": wipo_years,
        "treaty_article":        wipo_article,
        "compliant":             compliant,
        "margin_years":          margin,
        "local_path":            local_path,
        "doc_title":             doc_title,
        "source_url":            source_url,
        "eid":                   eid,
        "passage":               passage,
    }


def list_countries() -> list[dict]:
    """Return all countries in the KG with their duration data for the compliance overview."""
    return [{"code": c, "name": n} for c, n in _ALL_COUNTRIES.items()]


def _pick_span(passage: str, csv_duration: str) -> str:
    """Find a span in *passage* that matches the CSV duration value.

    e.g. "70 years pma" → searches passage for "70 years after…" phrase.
    Falls back to csv_duration if nothing matches.
    """
    import re
    # Extract the number from CSV duration ("70 years pma" → 70)
    m = re.search(r"(\d+)\s+years", csv_duration, re.IGNORECASE)
    if not m:
        return csv_duration
    num = m.group(1)
    # Find the phrase "N years …" in the passage (up to ~50 chars)
    pat = re.compile(rf"{num}\s+years[^.;,]{{0,60}}", re.IGNORECASE)
    found = pat.search(passage)
    return found.group(0).strip() if found else csv_duration
