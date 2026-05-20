"""Task 3: Visualization Specification Agent.

Takes the user's original question, the Task 1 enriched context, the KG
evidence payload, and the Task 2 answer, and produces a visualization spec
JSON dict that the UI can consume directly.
"""

from __future__ import annotations

import json

from scripts.chatbot_query_context import EnrichedUserQuery
from scripts.mock_kg_evidence import KGEvidence


_VIZ_TYPE: dict[str, str] = {
    "copyright duration": "rule_card",
    "economic rights": "rights_list",
    "personal-use exception": "yes_no_exception",
}

_DISPLAY_VALUE: dict[str, str] = {
    "life_plus_70": "Life of author + 70 years",
    "life_plus_50": "Life of author + 50 years",
    "list": "Multiple rights recognized",
    "yes": "Yes — exception provided",
    "no": "No — exception not provided",
    "unknown": "Unknown",
}


def generate_viz_spec(
    question: str,
    enriched_context: EnrichedUserQuery,
    evidence: KGEvidence,
    task2_answer: str,
) -> dict:
    """Return the Task 3 visualization spec as a dict."""
    ctx = enriched_context.get("extracted_context", {})
    rule_type = evidence.get("rule_type", ctx.get("Legal_Topic", "other"))
    jurisdiction = ctx.get("Jurisdiction", "")

    normalized_rule = evidence.get("normalized_rule") or {}
    normalized_value = normalized_rule.get("value", "unknown")

    document = evidence.get("document") or {}
    reference = evidence.get("reference") or {}
    ref_str = _format_reference(reference)

    return {
        "visualization_type": _viz_type(rule_type, normalized_value),
        "title": _make_title(rule_type, jurisdiction),
        "source_document": {
            "title": document.get("title", ""),
            "uri": document.get("local_path") or document.get("uri", ""),
            "reference": ref_str,
        },
        "rule": {
            "type": rule_type,
            "normalized_value": normalized_value,
            "display_value": _DISPLAY_VALUE.get(normalized_value, normalized_value),
        },
        "highlight": {
            "passage": evidence.get("passage", ""),
            "supporting_span": evidence.get("supporting_span", ""),
        },
    }


def generate_viz_spec_json(
    question: str,
    enriched_context: EnrichedUserQuery,
    evidence: KGEvidence,
    task2_answer: str,
) -> str:
    return json.dumps(
        generate_viz_spec(question, enriched_context, evidence, task2_answer),
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _viz_type(rule_type: str, normalized_value: str) -> str:
    return _VIZ_TYPE.get(rule_type, "document_highlight")


def _make_title(rule_type: str, jurisdiction: str) -> str:
    labels = {
        "copyright duration": "Copyright Duration",
        "economic rights": "Economic Rights",
        "personal-use exception": "Private Copy Exception",
    }
    label = labels.get(rule_type, rule_type.title())
    return f"{label} — {jurisdiction}" if jurisdiction else label


def _format_reference(reference: dict) -> str:
    article = reference.get("article", "")
    paragraph = reference.get("paragraph", "")

    ref = article
    if article and paragraph:
        ref = f"{article}({paragraph})"
    return ref or "—"
