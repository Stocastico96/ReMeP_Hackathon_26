"""Task 2: Evidence-Based Answer Agent (deterministic fallback).

Produces a grounded answer when no LLM key is available.
Used by llm_agent.generate_answer_llm as fallback.
"""

from __future__ import annotations

from scripts.chatbot_query_context import EnrichedUserQuery
from scripts.mock_kg_evidence import KGEvidence

_RIGHTS_LABELS = {
    "reproduction": "reproduce it (make copies)",
    "distribution": "distribute it (sell or give copies to the public)",
    "communication": "communicate it to the public (perform, broadcast, stream)",
    "rental":        "rent it out commercially",
    "translation":   "translate or adapt it",
}


def generate_answer(
    question: str,
    enriched_context: EnrichedUserQuery,
    evidence: KGEvidence,
) -> str:
    passage = evidence.get("passage", "")
    if not passage:
        return (
            "No supporting evidence was found in the knowledge graph for this query. "
            "Try specifying a jurisdiction (e.g. 'in Italy', 'under German law')."
        )

    ctx          = enriched_context.get("extracted_context", {})
    rule_type    = evidence.get("rule_type", "")
    jurisdiction = ctx.get("Jurisdiction", "")
    doc_link     = _format_document_link(evidence.get("document") or {})
    ref_str      = _format_reference(evidence.get("reference") or {})
    evidence_str = _format_evidence(passage, evidence.get("supporting_span") or "")

    # Jurisdiction note when WIPO is the fallback (user didn't specify a country)
    jurisdiction_note = ""
    if jurisdiction in ("WIPO", "Unknown", ""):
        jurisdiction_note = (
            "\n\n> **No country specified** — showing the international baseline "
            "(Berne Convention). Ask again mentioning a specific country (e.g. "
            '"What can I do with my songs in Italy?") for national law details.'
        )

    answer = _build_answer(rule_type, jurisdiction, evidence)

    return (
        f"Answer: {answer}{jurisdiction_note}\n\n"
        f"Document: {doc_link}\n\n"
        f"Reference: {ref_str}\n\n"
        f"Evidence: {evidence_str}"
    )


# ---------------------------------------------------------------------------
# Answer builders per rule type
# ---------------------------------------------------------------------------

def _build_answer(rule_type: str, jurisdiction: str, evidence: KGEvidence) -> str:
    if rule_type == "economic rights":
        return _build_rights_answer(jurisdiction, evidence)
    if rule_type == "copyright duration":
        return _build_duration_answer(jurisdiction, evidence)
    if rule_type == "personal-use exception":
        return _build_exception_answer(jurisdiction, evidence)
    return evidence.get("answer_candidate") or "—"


def _build_rights_answer(jurisdiction: str, evidence: KGEvidence) -> str:
    candidate = evidence.get("answer_candidate", "")
    # Extract rights list from candidate ("Italy grants: reproduction, distribution, ...")
    rights_raw = ""
    if "grants:" in candidate:
        rights_raw = candidate.split("grants:", 1)[1].strip().rstrip(".")
    elif "recognises" in candidate.lower():
        # Berne-style: "recognises the right of reproduction, translation..."
        rights_raw = candidate

    if rights_raw and "recognises" not in rights_raw.lower():
        rights = [r.strip() for r in rights_raw.split(",") if r.strip()]
        readable = [_RIGHTS_LABELS.get(r, r) for r in rights]
        jname = f"Under {jurisdiction} law, as" if jurisdiction not in ("WIPO", "Unknown", "") else "As"
        return (
            f"{jname} the author you have the exclusive right to:\n"
            + "\n".join(f"- **{r}**" for r in readable)
        )

    # Berne / fallback: rephrase in first person
    jname = f"Under {jurisdiction} law" if jurisdiction not in ("WIPO", "Unknown", "") else "Internationally"
    return (
        f"{jname}, as the author you hold exclusive rights over your work: "
        "you decide who can reproduce, distribute, adapt, or communicate it to the public. "
        "No one — including your cousin — can sell or distribute your songs without your authorisation."
    )


def _build_duration_answer(jurisdiction: str, evidence: KGEvidence) -> str:
    return evidence.get("answer_candidate") or "—"


def _build_exception_answer(jurisdiction: str, evidence: KGEvidence) -> str:
    return evidence.get("answer_candidate") or "—"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_document_link(document: dict) -> str:
    title = document.get("title") or "Document"
    path  = document.get("local_path") or document.get("uri") or ""
    return f"[{title}]({path})"


def _format_reference(reference: dict) -> str:
    article   = reference.get("article", "")
    paragraph = reference.get("paragraph", "")
    ref = article
    if article and paragraph:
        ref = f"{article}({paragraph})"
    return ref or "—"


def _format_evidence(passage: str, supporting_span: str) -> str:
    # Clean up excess whitespace from XML extraction
    import re
    passage = re.sub(r"\s+", " ", passage).strip()
    if supporting_span and supporting_span in passage:
        highlighted = passage.replace(supporting_span, f"<u>{supporting_span}</u>", 1)
    else:
        highlighted = passage
    return f'"{highlighted}"'
