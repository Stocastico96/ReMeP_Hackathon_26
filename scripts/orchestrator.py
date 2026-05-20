"""End-to-end pipeline: Task 1 → KG agent → Task 2 → Task 3.

Swap out ``_call_kg`` when Generoso's real KG agent is ready.
Everything else stays the same.

CLI usage:
    python3 scripts/orchestrator.py "What is the duration of copyright protection in Switzerland?"
"""

from __future__ import annotations

import argparse
import json

from scripts.chatbot_query_context import EnrichedUserQuery
from scripts.mock_kg_evidence import KGEvidence
from scripts.kg_query import query_kg
from scripts.llm_agent import enrich_query_llm, generate_answer_llm
from scripts.pydantic_models import SPARQLParams
from scripts.task3_viz_agent import generate_viz_spec


# ---------------------------------------------------------------------------
# KG interface — SPARQL-based retrieval from the legal KG
# ---------------------------------------------------------------------------

def _call_kg(enriched_context: EnrichedUserQuery) -> KGEvidence:
    ctx = enriched_context["extracted_context"]
    params = SPARQLParams.from_enriched(ctx)
    return query_kg(params)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def orchestrate(question: str) -> dict:
    """Run the full pipeline and return all four outputs."""
    enriched_context = enrich_query_llm(question)   # Task 1: LLM enrichment
    evidence = _call_kg(enriched_context)
    answer = generate_answer_llm(question, enriched_context, evidence)
    viz_spec = generate_viz_spec(question, enriched_context, evidence, answer)

    return {
        "enriched_context": enriched_context,
        "evidence": evidence,
        "answer": answer,
        "viz_spec": viz_spec,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="User's legal question.")
    parser.add_argument(
        "--output",
        choices=["all", "answer", "viz"],
        default="all",
        help="What to print: all outputs (default), only the answer, or only the viz spec.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = orchestrate(args.question)

    if args.output == "answer":
        print(result["answer"])
    elif args.output == "viz":
        print(json.dumps(result["viz_spec"], ensure_ascii=False, indent=2))
    else:
        print("=== Task 1 — Enriched Context ===")
        print(json.dumps(result["enriched_context"], ensure_ascii=False, indent=2))
        print("\n=== KG Evidence ===")
        print(json.dumps(result["evidence"], ensure_ascii=False, indent=2))
        print("\n=== Task 2 — Answer ===")
        print(result["answer"])
        print("\n=== Task 3 — Viz Spec ===")
        print(json.dumps(result["viz_spec"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
