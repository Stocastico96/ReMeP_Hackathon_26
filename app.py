"""ReMeP Legal Chatbot — Flask web app."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # reads OPENROUTER_API_KEY from .env if present

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, render_template, request, send_from_directory

from scripts.doc_extractor import extract_article_html, extract_full_doc_html, find_pdf_path
from scripts.kg_graph import graph_for
from scripts.kg_query import check_compliance, list_countries
from scripts.orchestrator import orchestrate
from scripts.point_in_time import get_version_at, list_versions  # noqa: F401 (used by routes)

app = Flask(__name__)
BASE_DIR = Path(__file__).parent


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/files/<path:filepath>")
def serve_file(filepath: str):
    """Serve data files (PDF, XML) directly."""
    return send_from_directory(BASE_DIR, filepath)


@app.post("/api/ask")
def ask():
    data = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Empty question"}), 400

    result = orchestrate(question)
    evidence = result["evidence"]
    doc = evidence.get("document", {})
    ref = evidence.get("reference", {})
    local_path = doc.get("local_path", "")

    span     = evidence.get("supporting_span", "")
    eid      = ref.get("eid", "")

    doc_html      = extract_article_html(local_path=local_path, eid=eid, supporting_span=span)
    full_doc_html = extract_full_doc_html(local_path=local_path, eid=eid, supporting_span=span)

    pdf_path = find_pdf_path(local_path)
    pdf_url  = f"/files/{pdf_path}" if pdf_path else ""

    from scripts.akn_metadata import extract_frbr
    meta = extract_frbr(local_path)

    return jsonify({
        "answer": result["answer"],
        "viz_spec": result["viz_spec"],
        "doc_html": doc_html,
        "full_doc_html": full_doc_html,
        "pdf_url": pdf_url,
        "frbr_work_uri":   meta["frbr_work_uri"],
        "point_in_time":   meta["point_in_time"],
        "is_authoritative": meta["is_authoritative"],
        "evidence": {
            "document": doc,
            "reference": ref,
            "passage": evidence.get("passage", ""),
            "supporting_span": evidence.get("supporting_span", ""),
        },
    })


@app.get("/api/countries")
def get_countries():
    return jsonify(list_countries())


def _csv_source_url(country_code: str) -> str:
    """Publisher URL for a jurisdiction, read from the knowledge graph."""
    from scripts.kg_builder import EX, LEGAL
    from scripts.kg_query import _get_graph
    node = EX[f"{country_code}_duration"]
    return str(next(iter(_get_graph().objects(node, LEGAL.sourceUrl)), ""))


@app.get("/api/graph/<country_code>")
def get_graph(country_code: str):
    """Nodes, edges, triples and the SPARQL query behind one jurisdiction."""
    data = graph_for(country_code.upper())
    if not data["nodes"]:
        return jsonify({"error": f"No graph for {country_code.upper()}", **data}), 404
    return jsonify(data)


@app.get("/api/versions/<country_code>")
def get_versions(country_code: str):
    return jsonify(list_versions(country_code.upper()))


@app.post("/api/document")
def get_document_at():
    """Retrieve an AKN article at a specific point in time."""
    data        = request.get_json(force=True)
    country     = (data.get("country_code") or "").strip().upper()
    eid         = (data.get("eid")          or "").strip()
    target_date = (data.get("date")         or "").strip()
    span        = (data.get("span")         or "").strip()

    if not country or not eid:
        return jsonify({"error": "Missing country_code or eid"}), 400

    versions = list_versions(country)

    # A date before the first available version has no document at all. Saying so
    # is better than silently serving today's text for a date in 1935.
    if target_date and versions and target_date < versions[0]["date"]:
        return jsonify({
            "error": (
                f"No version of this act exists for {target_date}. The earliest "
                f"available version is {versions[0]['date']}."
            ),
            "earliest_version": versions[0]["date"],
            "latest_version":   versions[-1]["date"],
        }), 404

    # Resolve file path: versioned if date given, else current canonical
    versioned = get_version_at(country, target_date) if target_date else None
    if versioned:
        local_path = str(versioned)
    else:
        from scripts.kg_builder import _JURISDICTION_FILES
        local_path = _JURISDICTION_FILES.get(country, {}).get("local_path", "")

    if not local_path:
        return jsonify({"error": f"No document for {country}"}), 404

    # Which version actually answered the request — the date the user typed is
    # rarely the date a version came into force.
    resolved = ""
    if versioned:
        for entry in versions:
            if entry["file"] == versioned.name:
                resolved = entry["date"]
                break

    doc_html      = extract_article_html(local_path=local_path, eid=eid, supporting_span=span)
    full_doc_html = extract_full_doc_html(local_path=local_path, eid=eid, supporting_span=span)
    pdf_path      = find_pdf_path(local_path)

    # A provision missing from an older version has not been enacted yet — that is
    # a legal fact, not a lookup failure, so say so instead of "not found".
    if target_date and "doc-error" in doc_html:
        doc_html = (
            f'<p class="doc-error">This provision is not part of the version in '
            f'force on {target_date}. It was introduced by a later amendment.</p>'
        )

    from scripts.akn_metadata import extract_frbr
    meta = extract_frbr(local_path)

    return jsonify({
        "local_path":     local_path,
        "doc_html":       doc_html,
        "full_doc_html":  full_doc_html,
        "version_date":   resolved,
        "version_count":  len(versions),
        "source_url":     meta["source_uri"] or _csv_source_url(country),
        "pdf_url":        f"/files/{pdf_path}" if pdf_path else "",
        "point_in_time":  meta["point_in_time"] or target_date,
        "frbr_work_uri":  meta["frbr_work_uri"],
        "is_authoritative": meta["is_authoritative"],
    })


@app.post("/api/compliance")
def compliance():
    data = request.get_json(force=True)
    country_code = (data.get("country_code") or "").strip().upper()
    if not country_code:
        return jsonify({"error": "Missing country_code"}), 400

    result = check_compliance(country_code)
    if "error" in result:
        return jsonify(result), 404

    local_path = result.get("local_path", "")
    eid        = result.get("eid", "")

    doc_html      = extract_article_html(local_path=local_path, eid=eid, supporting_span="")
    full_doc_html = extract_full_doc_html(local_path=local_path, eid=eid, supporting_span="")
    pdf_path      = find_pdf_path(local_path)
    pdf_url       = f"/files/{pdf_path}" if pdf_path else ""

    from scripts.akn_metadata import extract_frbr
    meta = extract_frbr(local_path)

    return jsonify({
        **result,
        "doc_html":        doc_html,
        "full_doc_html":   full_doc_html,
        "pdf_url":         pdf_url,
        "frbr_work_uri":   meta["frbr_work_uri"],
        "point_in_time":   meta["point_in_time"],
        "is_authoritative": meta["is_authoritative"],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050)
