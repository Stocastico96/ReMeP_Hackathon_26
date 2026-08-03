"""OpenRouter LLM agents for Task 1 (query enrichment) and Task 2 (answer generation).

Requires the OPENROUTER_API_KEY environment variable.
Both functions fall back to deterministic implementations when the key is absent.
"""

from __future__ import annotations

import json
import os

from scripts.mock_kg_evidence import KGEvidence
from scripts.chatbot_query_context import EnrichedUserQuery, ExtractedContext, SPARQL_ENRICHMENT_PHRASE

# google/gemini-2.0-flash-001 was retired by OpenRouter (404: no endpoints found).
# Models are tried in order: paid Gemini Flash first, then free-tier Gemma as a
# safety net if the account runs out of credits. The free models are also capped
# per day account-wide, so they are not reliable enough to lead the list.
# Override with a comma-separated OPENROUTER_MODEL list in .env if needed.
_DEFAULT_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
]
_MODELS = [
    m.strip()
    for m in os.environ.get("OPENROUTER_MODEL", ",".join(_DEFAULT_MODELS)).split(",")
    if m.strip()
]
_MODEL = _MODELS[0]  # kept for backwards compatibility / logging

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
        # flush: without it these warnings sit in the buffer while the server
        # runs, and the silent fallback looks like a working LLM
        print(f"[llm_agent] enrich failed, using deterministic fallback: {exc}", flush=True)
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
    response = _chat(
        client,
        messages=[
            {"role": "system", "content": _ENRICH_SYSTEM},
            {"role": "user",   "content": question},
        ],
        max_tokens=1024,
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(_strip_code_fence(raw))

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
- Write the answer in the SAME LANGUAGE as the user's question, even though the evidence \
may be in another language.
- Do NOT invent information not present in the evidence.
- Start directly with the answer; do not repeat the question.
- Cite the article reference at the end in parentheses, e.g. (Art. 29 URG).

About the evidence fields:
- "answer_candidate" is the value encoded in the knowledge graph and verified by lawyers. \
It is authoritative. Build your answer on it.
- "passage" is the text of the cited provision as published. Consolidated sources sometimes \
keep the original wording and record later amendments as a separate note, so the passage may \
literally state an older figure than answer_candidate. That is not a contradiction: trust \
answer_candidate and, if the passage carries such an amendment note, mention that the figure \
was changed by the amendment.
- Reply "No supporting evidence was found in the knowledge graph." ONLY when both \
answer_candidate and passage are empty strings. Never use that sentence when either holds text.
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
        print(f"[llm_agent] answer failed, using deterministic fallback: {exc}", flush=True)
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

    response = _chat(
        client,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=1024,
        temperature=0.1,
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _strip_code_fence(raw: str) -> str:
    """Drop a ```json ... ``` wrapper, which some models add despite json_object."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _chat(client, **kwargs):
    """Call chat.completions over _MODELS in order, returning the first success.

    Free-tier models are rate-limited upstream (HTTP 429), so a single model is
    not reliable enough on its own.
    """
    last_exc: Exception | None = None
    for model in _MODELS:
        try:
            response = client.chat.completions.create(model=model, **kwargs)
            if (response.choices[0].message.content or "").strip():
                return response
            last_exc = RuntimeError(f"{model} returned empty content")
        except Exception as exc:  # noqa: BLE001 — try the next model
            last_exc = exc
            print(f"[llm_agent] {model} unavailable: {str(exc)[:160]}", flush=True)
    raise last_exc if last_exc else RuntimeError("no models configured")


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
