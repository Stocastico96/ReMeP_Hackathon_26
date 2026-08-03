"""Expose a jurisdiction's subgraph for the Knowledge Graph view.

The web UI needs three things to make the symbolic layer inspectable:

  1. a node/edge structure it can draw,
  2. the raw triples behind every node, so a claim can be traced to the graph,
  3. the SPARQL query that produced them.

Node types mirror the legend used in the paper: Country, Law, Rule, Article,
Duration, Right, Treaty.
"""

from __future__ import annotations

from rdflib import Literal, URIRef

from scripts.kg_builder import EX, IPRONTO, LEGAL
from scripts.kg_query import _get_graph
from scripts.sparql_generator import PREFIXES

_BERNE = EX["WIPO_berne_art7"]

# Every triple of every node belonging to one jurisdiction, plus the Berne
# baseline it is compared against.
SUBGRAPH_QUERY = """\
SELECT ?node ?predicate ?object
WHERE {
  { ?node legal:jurisdiction "%s" }
  UNION
  { ?node legal:jurisdiction "WIPO" }
  UNION
  { ex:%s_rights legal:hasRightDetail ?node }
  ?node ?predicate ?object .
}
ORDER BY ?node ?predicate
"""


def sparql_for(code: str) -> str:
    """The query the view runs, ready to display next to the graph."""
    return PREFIXES + SUBGRAPH_QUERY % (code, code)


def graph_for(code: str) -> dict:
    """Return {nodes, edges, triples, sparql} for one jurisdiction."""
    code = (code or "").strip().upper()
    if not code:
        return {"nodes": [], "edges": [], "triples": [], "sparql": ""}

    g = _get_graph()
    duration  = EX[f"{code}_duration"]
    rights    = EX[f"{code}_rights"]
    exception = EX[f"{code}_exception"]

    if (duration, LEGAL.jurisdiction, Literal(code)) not in g:
        return {"nodes": [], "edges": [], "triples": [], "sparql": sparql_for(code)}

    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(nid: str, label: str, kind: str, sub: str = "", uri: URIRef | None = None) -> str:
        if nid in seen:
            return nid
        seen.add(nid)
        nodes.append({
            "id": nid, "label": label, "type": kind, "sublabel": sub,
            "triples": _triples_of(g, uri) if uri is not None else [],
        })
        return nid

    def add_edge(src: str, dst: str, label: str) -> None:
        edges.append({"source": src, "target": dst, "label": label})

    country_name = _one(g, duration, LEGAL.jurisdictionName) or code
    add_node("country", country_name, "country", code)

    # One law node per distinct source document: the EU keeps the term of
    # protection in Directive 2006/116 and the rights in InfoSoc 2001/29, and the
    # graph should show that rather than pretend there is a single instrument.
    law_ids: dict[str, str] = {}

    def law_for(rule_node) -> str:
        title = _one(g, rule_node, LEGAL.docTitle) or "Unknown source"
        if title not in law_ids:
            nid = f"law_{len(law_ids) + 1}"
            law_ids[title] = nid
            add_node(nid, title, "law", _one(g, rule_node, LEGAL.frbrWorkUri))
            add_edge("country", nid, "governs")
        return law_ids[title]

    # ── copyright duration ────────────────────────────────────────────────
    years    = _one(g, duration, LEGAL.durationYears)
    literary = _one(g, duration, LEGAL.durationLiterary)
    add_node("rule_duration", "Copyright duration", "rule",
             _one(g, duration, LEGAL.ruleType), duration)
    add_edge(law_for(duration), "rule_duration", "contains")

    art = _one(g, duration, LEGAL.articleRef)
    if art:
        add_node("art_duration", art, "article")
        add_edge("rule_duration", "art_duration", "expresses")

    if years:
        add_node("duration_value", f"{years} years", "duration", literary)
        add_edge("rule_duration", "duration_value", "hasDuration")

    # ── treaty baseline ───────────────────────────────────────────────────
    if (duration, LEGAL.compliesWith, _BERNE) in g:
        berne_years = _one(g, _BERNE, LEGAL.durationYears)
        add_node("treaty", _one(g, _BERNE, LEGAL.articleRef) or "Berne Art. 7", "treaty",
                 f"min. {berne_years} years pma", _BERNE)
        add_edge("rule_duration", "treaty", "compliesWith")

    # ── economic rights ───────────────────────────────────────────────────
    if (rights, LEGAL.jurisdiction, Literal(code)) in g:
        add_node("rule_rights", "Economic rights", "rule",
                 _one(g, rights, LEGAL.ruleType), rights)
        add_edge(law_for(rights), "rule_rights", "contains")

        art = _one(g, rights, LEGAL.articleRef)
        if art:
            add_node("art_rights", art, "article")
            add_edge("rule_rights", "art_rights", "expresses")

        for detail in sorted(g.objects(rights, LEGAL.hasRightDetail)):
            name = _one(g, detail, LEGAL.rightName) or str(detail).rsplit("_", 1)[-1]
            ref  = _one(g, detail, LEGAL.articleRef)
            nid  = f"right_{name}"
            add_node(nid, name.capitalize(), "right", ref, detail)
            add_edge("rule_rights", nid, "hasRight")

    # ── personal-use exception ────────────────────────────────────────────
    if (exception, LEGAL.jurisdiction, Literal(code)) in g:
        has_exc = _one(g, exception, LEGAL.hasException) == "true"
        add_node("rule_exception", "Private-copy exception", "rule",
                 "yes" if has_exc else "no", exception)
        add_edge(law_for(exception), "rule_exception", "contains")

        art = _one(g, exception, LEGAL.articleRef)
        if art:
            add_node("art_exception", art, "article")
            add_edge("rule_exception", "art_exception", "expresses")

    return {
        "nodes": nodes,
        "edges": edges,
        "triples": _triples_of(g, duration),
        "sparql": sparql_for(code),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _one(g, subject, predicate) -> str:
    for value in g.objects(subject, predicate):
        return str(value)
    return ""


def _triples_of(g, subject: URIRef) -> list[dict]:
    """All triples of *subject*, shortened for display."""
    out = []
    for predicate, obj in sorted(g.predicate_objects(subject)):
        out.append({
            "subject":   _short(subject),
            "predicate": _short(predicate),
            "object":    _short(obj),
        })
    return out


_PREFIX_MAP = {
    str(EX):      "ex:",
    str(LEGAL):   "legal:",
    str(IPRONTO): "ipronto:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
}


def _short(term) -> str:
    text = str(term)
    for namespace, prefix in _PREFIX_MAP.items():
        if text.startswith(namespace):
            return prefix + text[len(namespace):]
    return text
