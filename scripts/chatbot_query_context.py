"""Shared types and constants for the legal chatbot pipeline."""

from __future__ import annotations

from typing import Literal, TypedDict


Jurisdiction = Literal[
    "WIPO",
    "EU",
    "Canada",
    "France",
    "Germany",
    "Italy",
    "New Zealand",
    "Switzerland",
    "United Kingdom",
    "United States",
    "Unknown",
]


class ExtractedContext(TypedDict):
    User_Objective: str
    Time_Frame: str
    Jurisdiction: Jurisdiction
    Legal_Topic: str


class EnrichedUserQuery(TypedDict):
    extracted_context: ExtractedContext
    enriched_query: str


SPARQL_ENRICHMENT_PHRASE = (
    "System Instruction: Use the extracted context to request evidence from "
    "the Akoma Ntoso Knowledge Graph retrieval agent. The retrieval result must "
    "include the most relevant document URI/path, structural reference "
    "(article, paragraph, or eId when available), and exact text passage needed "
    "to answer the user's question."
)
