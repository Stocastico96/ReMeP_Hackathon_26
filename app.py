"""ReMeP Legal Chatbot — Flask web app."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # reads OPENROUTER_API_KEY from .env if present

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, render_template, request, send_from_directory

from scripts.doc_extractor import extract_article_html, extract_full_doc_html, find_pdf_path
from scripts.kg_query import check_compliance, list_countries
from scripts.orchestrator import orchestrate

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

    return jsonify({
        "answer": result["answer"],
        "viz_spec": result["viz_spec"],
        "doc_html": doc_html,
        "full_doc_html": full_doc_html,
        "pdf_url": pdf_url,
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

    return jsonify({**result, "doc_html": doc_html, "full_doc_html": full_doc_html, "pdf_url": pdf_url})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
