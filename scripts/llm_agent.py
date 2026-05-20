"""OpenRouter LLM agents for Task 1 (query enrichment) and Task 2 (answer generation).

Requires the OPENROUTER_API_KEY environment variable.
Both functions fall back to deterministic implementations when the key is absent.
"""

from __future__ import annotations

import json
import os

from scripts.mock_kg_evidence import KGEvidence
from scripts.chatbot_query_context import EnrichedUserQuery, ExtractedContext, SPARQL_ENRICHMENT_PHRASE

_MODEL = "google/gemini-2.0-flash-001"

# ---------------------------------------------------------------------------
# Task 1 — LLM-based query enrichment
# ---------------------------------------------------------------------------

_ENRICH_SYSTEM = """\
You are a legal information extraction assistant specialising in intellectual property law.

Given a user question in ANY language, extract the following fields and return ONLY a valid \
JSON object (no markdown, no explanation):

{
  "User_Objective": "<one sentence in English rephrasing what the user wants to know>",
  "Time_Frame": "<year range like '1990-2020' or 'Current' if not specified>",
  "Jurisdiction": "<one of: WIPO, EU, Canada, France, Germany, Italy, New Zealand, Switzerland, United Kingdom, United States, Unknown>",
  "Legal_Topic": "<one of: copyright duration, economic rights, personal-use exception, performers' rights, phonograms, broadcasting, trademarks, patents, industrial designs, geographical indications, appellations of origin, accessibility exceptions, intellectual property>"
}

Rules for "Jurisdiction":
- Detect country names in any language: "Francia/France/Frankreich" → "France", \
  "Italia/Italy/Italien" → "Italy", "Germania/Germany/Deutschland" → "Germany", \
  "Svizzera/Switzerland" → "Switzerland", "Regno Unito/United Kingdom/UK" → "United Kingdom", \
  "Stati Uniti/United States/USA" → "United States", "Canada" → "Canada", \
  "Nuova Zelanda/New Zealand" → "New Zealand".
- Berne Convention, WIPO, international treaty → "WIPO".
- EU Directive, European Union → "EU".
- No country mentioned → "Unknown".

Rules for "Legal_Topic" — read carefully, this is the most important field:
- "copyright duration" → ANY question about WHEN protection EXPIRES or HOW LONG it lasts: \
  "scade" (Italian: expires), "quando scade" (when does it expire), "durata" (duration), \
  "termine" (term), "quanti anni" (how many years), "how long", "expire", "term of protection", \
  "Schutzfrist" (German), "durée" (French), "after death", "post mortem".
- "economic rights" → questions about WHAT rights an author HAS or CAN DO: \
  "che diritti ho" (what rights do I have), "cosa posso fare" (what can I do), \
  "reproduction", "distribution", "communication to the public", "making available", \
  "exclusive rights", "my cousin sell", "venderla" (sell it).
- "personal-use exception" → private copy, personal use, fair use, exceptions to rights: \
  "copia privata", "uso personale", "private copy", "can I download", "fair use".
- If the question contains BOTH a duration signal AND an economic-rights signal, prefer \
  "copyright duration" when "scade/expire/when/how long" appears.
- Default → "intellectual property".

Examples:
- "quando scade il diritto d'autore in Francia?" → Jurisdiction: France, Legal_Topic: copyright duration
- "che diritti ho in Italia se scrivo una canzone?" → Jurisdiction: Italy, Legal_Topic: economic rights
- "can I copy a book for personal use in Germany?" → Jurisdiction: Germany, Legal_Topic: personal-use exception
- "what is the copyright term under the Berne Convention?" → Jurisdiction: WIPO, Legal_Topic: copyright duration
- "quando scade la proprietà intellettuale in Francia?" → Jurisdiction: France, Legal_Topic: copyright duration
"""


def enrich_query_llm(question: str) -> EnrichedUserQuery:
    """Use LLM to extract structured context from the user question."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return _no_key_context(question)

    try:
        return _call_enrich(api_key, question)
    except Exception as exc:
        print(f"[llm_agent] enrich failed: {exc}")
        return _no_key_context(question)


def _no_key_context(question: str) -> EnrichedUserQuery:
    """Minimal context returned when no API key is configured."""
    return {
        "extracted_context": {
            "User_Objective": question,
            "Time_Frame": "Current",
            "Jurisdiction": "Unknown",
            "Legal_Topic": "intellectual property",
        },
        "enriched_query": f"{question.strip()} {SPARQL_ENRICHMENT_PHRASE}",
    }


def _call_enrich(api_key: str, question: str) -> EnrichedUserQuery:
    from openai import OpenAI
    from scripts.chatbot_query_context import SPARQL_ENRICHMENT_PHRASE

    client = _make_client(api_key)
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _ENRICH_SYSTEM},
            {"role": "user",   "content": question},
        ],
        max_tokens=256,
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)

    extracted: ExtractedContext = {
        "User_Objective": data.get("User_Objective", question),
        "Time_Frame":     data.get("Time_Frame", "Current"),
        "Jurisdiction":   data.get("Jurisdiction", "Unknown"),
        "Legal_Topic":    data.get("Legal_Topic", "intellectual property"),
    }
    return {
        "extracted_context": extracted,
        "enriched_query": f"{question.strip()} {SPARQL_ENRICHMENT_PHRASE}",
    }


# ---------------------------------------------------------------------------
# Task 2 — LLM-based answer generation
# ---------------------------------------------------------------------------

_ANSWER_SYSTEM = """\
You are a precise legal information assistant specialising in copyright and intellectual property law.
You receive a user question and evidence retrieved from a legal knowledge graph.

Your task:
- Give a concise, accurate answer grounded strictly in the retrieved evidence (2-4 sentences).
- Do NOT invent information not present in the evidence.
- Start directly with the answer; do not repeat the question.
- Cite the article reference at the end in parentheses, e.g. (Art. 29 URG).
- If the passage is empty, reply: "No supporting evidence was found in the knowledge graph."
"""


def generate_answer_llm(
    question: str,
    enriched_context: EnrichedUserQuery,
    evidence: KGEvidence,
) -> str:
    """Call OpenRouter to generate a natural-language answer grounded in KG evidence."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        from scripts.task2_answer_agent import generate_answer
        return generate_answer(question, enriched_context, evidence)

    try:
        return _call_answer(api_key, question, enriched_context, evidence)
    except Exception as exc:
        print(f"[llm_agent] answer failed: {exc}")
        from scripts.task2_answer_agent import generate_answer
        return generate_answer(question, enriched_context, evidence)


def _call_answer(
    api_key: str,
    question: str,
    enriched_context: EnrichedUserQuery,
    evidence: KGEvidence,
) -> str:
    from openai import OpenAI

    client = _make_client(api_key)
    ctx = enriched_context.get("extracted_context", {})
    user_content = json.dumps(
        {
            "question":    question,
            "jurisdiction": ctx.get("Jurisdiction", ""),
            "legal_topic":  ctx.get("Legal_Topic", ""),
            "evidence": {
                "answer_candidate": evidence.get("answer_candidate", ""),
                "passage":          evidence.get("passage", ""),
                "supporting_span":  evidence.get("supporting_span", ""),
                "article_ref":      evidence.get("reference", {}).get("article", ""),
                "doc_title":        evidence.get("document", {}).get("title", ""),
            },
        },
        ensure_ascii=False,
        indent=2,
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=512,
        temperature=0.1,
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _make_client(api_key: str):
    from openai import OpenAI
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://remep-hackathon-2026.local",
            "X-Title": "ReMeP Legal KG Chatbot",
        },
    )
